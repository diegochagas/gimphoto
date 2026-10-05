import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gimp_default_accels  # noqa: E402
import make_keymap  # noqa: E402

DEFAULTS = {
    "image-duplicate": ["<primary>D"],
    "select-none": ["<primary><shift>A"],
    "layers-duplicate": ["<primary><shift>D"],
    "tools-move": ["M"],
    "tools-rect-select": ["R"],
    "edit-paste-in-place": ["<primary><alt>V", "<alt>Paste"],
    "edit-paste-as-new-image": ["<primary><shift>V", "<shift>Paste"],
    "file-quit": ["<primary>Q"],
}


def keymap(text):
    return make_keymap.read_keymap(text.replace("|", "\t"))


class Normalize(unittest.TestCase):
    def test_spellings_of_one_key_are_equal(self):
        self.assertEqual(make_keymap.normalize("<Control>D"), make_keymap.normalize("<primary>d"))
        self.assertEqual(make_keymap.normalize("<shift><Primary>a"), make_keymap.normalize("<Primary><Shift>A"))

    def test_different_modifiers_differ(self):
        self.assertNotEqual(make_keymap.normalize("<primary>d"), make_keymap.normalize("<primary><shift>d"))

    def test_human_names_for_the_docs(self):
        self.assertEqual(make_keymap.human("<Primary><Shift>bracketright"), "Ctrl+Shift+]")
        self.assertEqual(make_keymap.human("<shift><alt><primary>w"), "Ctrl+Alt+Shift+W")
        self.assertEqual(make_keymap.human("<Alt>BackSpace"), "Alt+Backspace")
        self.assertEqual(make_keymap.human("F7"), "F7")

    def test_garbage_is_rejected(self):
        for bad in ["", "<primary>", "<hyper>d", "<primary>d x"]:
            with self.assertRaises(ValueError, msg=bad):
                make_keymap.normalize(bad)


class ReadKeymap(unittest.TestCase):
    def test_rows_comments_and_several_shortcuts(self):
        rows = keymap("# comment\n\nselect-none|<Primary>d|Deselect\nedit-clear|BackSpace,Delete|Clear\n")
        self.assertEqual(
            rows, [("select-none", ["<Primary>d"], "Deselect"), ("edit-clear", ["BackSpace", "Delete"], "Clear")]
        )

    def test_a_row_without_three_fields_is_an_error(self):
        with self.assertRaises(ValueError):
            keymap("select-none|<Primary>d\n")


class Build(unittest.TestCase):
    def test_taken_key_leaves_its_gimp_action(self):
        out = make_keymap.build(keymap("select-none|<Primary>d|Deselect\n"), DEFAULTS)
        self.assertEqual(out["image-duplicate"], [])

    def test_mapped_action_keeps_its_free_gimp_shortcuts(self):
        out = make_keymap.build(keymap("select-none|<Primary>d|Deselect\n"), DEFAULTS)
        self.assertEqual(out["select-none"], ["<Primary>d", "<primary><shift>A"])

    def test_other_action_keeps_its_other_shortcuts(self):
        out = make_keymap.build(keymap("edit-paste-in-place|<Primary><Shift>v|Paste in Place\n"), DEFAULTS)
        self.assertEqual(out["edit-paste-as-new-image"], ["<shift>Paste"])
        self.assertEqual(out["edit-paste-in-place"], ["<Primary><Shift>v", "<primary><alt>V", "<alt>Paste"])

    def test_tool_keys_move(self):
        out = make_keymap.build(keymap("tools-move|v|Move\ntools-rect-select|m|Marquee\n"), DEFAULTS)
        self.assertEqual(out["tools-move"], ["v"])
        self.assertEqual(out["tools-rect-select"], ["m", "R"])

    def test_text_tool_actions_are_left_alone(self):
        defaults = {**DEFAULTS, "text-tool-toggle-bold": ["<primary>B"], "dialogs-toolbox": ["<primary>B"]}
        out = make_keymap.build(keymap("select-none|<Primary>b|Deselect\n"), defaults)
        self.assertNotIn("text-tool-toggle-bold", out)
        self.assertEqual(out["dialogs-toolbox"], [])

    def test_untouched_actions_are_not_written(self):
        out = make_keymap.build(keymap("select-none|<Primary>d|Deselect\n"), DEFAULTS)
        self.assertNotIn("file-quit", out)
        self.assertNotIn("tools-move", out)

    def test_no_key_does_two_things(self):
        rows = keymap("select-none|<Primary>d|Deselect\nlayers-duplicate|<primary>D|Duplicate\n")
        with self.assertRaises(ValueError):
            make_keymap.build(rows, DEFAULTS)

    def test_unknown_action_is_an_error(self):
        with self.assertRaises(ValueError):
            make_keymap.build(keymap("select-nothing|<Primary>d|Deselect\n"), DEFAULTS)

    def test_an_action_twice_is_an_error(self):
        with self.assertRaises(ValueError):
            make_keymap.build(keymap("select-none|<Primary>d|Deselect\nselect-none|<Primary>e|Again\n"), DEFAULTS)

    def test_render_is_gimps_format(self):
        text = make_keymap.render({"select-none": ["<Primary>d"], "image-duplicate": []})
        self.assertIn("(file-version 1)\n", text)
        self.assertIn('(action "image-duplicate")\n(action "select-none" "<Primary>d")\n', text)


class TheRealKeymap(unittest.TestCase):
    """defaults/photoshop-keymap.tsv itself, without GIMP's source."""

    def setUp(self):
        self.rows = make_keymap.read_keymap(make_keymap.KEYMAP.read_text())

    def test_every_shortcut_parses_and_none_repeats(self):
        keys = [make_keymap.normalize(a) for _, accels, _ in self.rows for a in accels]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_ctrl_d_report(self):
        # Ctrl+D duplicated the image (a new tab) instead of deselecting
        self.assertIn(("select-none", ["<Primary>d"], "Select > Deselect (Ctrl+D)"), self.rows)

    def test_generated_file_has_every_row(self):
        text = make_keymap.OUTPUT.read_text()
        for action, accels, _ in self.rows:
            self.assertIn(f'(action "{action}" "{accels[0]}"', text)


class DocsTable(unittest.TestCase):
    def test_only_the_part_between_markers_changes(self):
        doc = f"intro\n{make_keymap.DOC_START}old\n{make_keymap.DOC_END}\noutro\n"
        self.assertEqual(
            make_keymap.with_table(doc, "new\n"), f"intro\n{make_keymap.DOC_START}new\n{make_keymap.DOC_END}\noutro\n"
        )

    def test_the_page_has_its_markers(self):
        doc = make_keymap.DOC.read_text()
        self.assertIn(make_keymap.DOC_START, doc)
        self.assertIn(make_keymap.DOC_END, doc)


class Extractor(unittest.TestCase):
    def source(self, actions="", tools=""):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "app" / "actions").mkdir(parents=True)
        (tmp / "app" / "tools").mkdir(parents=True)
        (tmp / "app" / "actions" / "x-actions.c").write_text(actions)
        (tmp / "app" / "tools" / "x.c").write_text(tools)
        return tmp

    def test_action_entries(self):
        src = self.source(
            """static const GimpActionEntry x_actions[] =
{
  { "image-duplicate", GIMP_ICON_OBJECT_DUPLICATE,
    NC_("image-action", "_Duplicate"), NULL, { "<primary>D", NULL },
    NC_("image-action", "Create a duplicate of this image"),
    image_duplicate_cmd_callback,
    GIMP_HELP_IMAGE_DUPLICATE },

  { "image-properties", "dialog-information",
    NC_("image-action", "Image Pr_operties"), NULL, { "<alt>Return", NULL },
    NULL },

  { "edit-copy-visible", NULL, /* GIMP_ICON_COPY_VISIBLE, */
    NC_("edit-action", "Copy _Visible"), NULL, { "<primary><shift>C", "<shift>Copy", NULL },
    NULL },

  { "file-export", NULL,
    NC_("file-action", "Export"), NULL, { NULL }, NULL },
};
"""
        )
        self.assertEqual(
            gimp_default_accels.default_accels(src),
            {
                "image-duplicate": ["<primary>D"],
                "image-properties": ["<alt>Return"],
                "edit-copy-visible": ["<primary><shift>C", "<shift>Copy"],
                "file-export": [],
            },
        )

    def test_accel_lists_that_look_like_entries(self):
        # { "1", "KP_1", NULL } and { "plus", ... } are shortcuts, not actions
        src = self.source(
            """static const GimpRadioActionEntry x[] =
{
  { "view-zoom-1-1", GIMP_ICON_ZOOM_ORIGINAL,
    NC_("view-zoom-action", "Zoom 1:1 (100%)"),
    NC_("view-zoom-action", "_1:1  (100%)"),
    { "1", "KP_1", NULL },
    NULL },

  { "view-zoom-in", GIMP_ICON_ZOOM_IN,
    NC_("view-zoom-action", "Zoom _In"), NULL, { "plus", "KP_Add", "ZoomIn", NULL },
    NULL },
};
"""
        )
        self.assertEqual(
            gimp_default_accels.default_accels(src),
            {"view-zoom-1-1": ["1", "KP_1"], "view-zoom-in": ["plus", "KP_Add", "ZoomIn"]},
        )

    def test_accel_macros(self):
        src = self.source(
            """#ifndef PLATFORM_OSX
#define NEXT_ACCEL "<alt>Tab"
#else
#define NEXT_ACCEL "<primary>grave"
#endif
static const GimpActionEntry x[] =
{
  { "windows-show-display-next", NULL,
    NC_("windows-action", "Next Image"), NULL, { NEXT_ACCEL, "Forward", NULL },
    NULL },
};
"""
        )
        self.assertEqual(
            gimp_default_accels.default_accels(src), {"windows-show-display-next": ["<alt>Tab", "Forward"]}
        )

    def test_tools(self):
        src = self.source(
            tools="""  (* callback) (GIMP_TYPE_RECTANGLE_SELECT_TOOL,
                "gimp-rect-select-tool",
                _("Rectangle Select"),
                _("Rectangle Select Tool: Select a rectangular region"),
                N_("_Rectangle Select"), "R",
                NULL, GIMP_HELP_TOOL_RECT_SELECT,
                GIMP_ICON_TOOL_RECT_SELECT,
                data);
  (* callback) (GIMP_TYPE_SMUDGE_TOOL,
                "gimp-smudge-tool",
                _("Smudge"),
                _("Smudge Tool"),
                N_("_Smudge"), NULL,
                NULL, GIMP_HELP_TOOL_SMUDGE,
                GIMP_ICON_TOOL_SMUDGE,
                data);
"""
        )
        self.assertEqual(gimp_default_accels.default_accels(src), {"tools-rect-select": ["R"], "tools-smudge": []})


if __name__ == "__main__":
    unittest.main()
