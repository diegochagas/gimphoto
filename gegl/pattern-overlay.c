/* gimphoto:pattern-overlay: Photoshop's Pattern Overlay layer effect.
 *
 * Tiles an image file where the input has pixels, keeping the input's
 * alpha; the layer filter's own blend mode and opacity mix it with the
 * layer. The tiling starts at the input's top-left corner, as Photoshop's
 * "Link with Layer".
 *
 * Part of GIMPhoto (https://github.com/diegochagas/gimphoto).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 */

#include <glib/gi18n-lib.h>
#include <math.h>

#ifdef GEGL_PROPERTIES

property_file_path (path, _("Pattern"), "")
  description (_("Image file tiled over the layer"))

property_double (scale, _("Scale"), 100.0)
  description (_("Size of the pattern, in percent"))
  value_range (1.0, 1000.0)

property_int (offset_x, _("Horizontal offset"), 0)
  value_range (-100000, 100000)
  ui_meta ("unit", "pixel-distance")

property_int (offset_y, _("Vertical offset"), 0)
  value_range (-100000, 100000)
  ui_meta ("unit", "pixel-distance")

#else

#define GEGL_OP_POINT_FILTER
#define GEGL_OP_NAME     pattern_overlay
#define GEGL_OP_C_SOURCE pattern-overlay.c

#include "gegl-op.h"

/* the pattern's pixels, loaded once per path */
typedef struct
{
  gchar  *path;
  gint    width;
  gint    height;
  gfloat *pixels;
} Pattern;

static void
pattern_free (Pattern *pattern)
{
  if (pattern)
    {
      g_free (pattern->path);
      g_free (pattern->pixels);
      g_free (pattern);
    }
}

static void
load_pattern (GeglProperties *o,
              const Babl     *format)
{
  Pattern    *pattern = o->user_data;
  GeglNode   *graph;
  GeglNode   *load;
  GeglNode   *sink;
  GeglBuffer *buffer = NULL;

  if (pattern && g_strcmp0 (pattern->path, o->path) == 0)
    return;

  pattern_free (pattern);
  o->user_data = pattern = g_new0 (Pattern, 1);
  pattern->path = g_strdup (o->path);

  if (! o->path || ! *o->path || ! g_file_test (o->path, G_FILE_TEST_IS_REGULAR))
    return;

  graph = gegl_node_new ();
  load  = gegl_node_new_child (graph,
                               "operation", "gegl:load",
                               "path",      o->path,
                               NULL);
  sink  = gegl_node_new_child (graph,
                               "operation", "gegl:buffer-sink",
                               "buffer",    &buffer,
                               NULL);
  gegl_node_link (load, sink);
  gegl_node_process (sink);
  g_object_unref (graph);

  if (buffer)
    {
      const GeglRectangle *extent = gegl_buffer_get_extent (buffer);

      if (extent->width > 0 && extent->height > 0)
        {
          pattern->width  = extent->width;
          pattern->height = extent->height;
          pattern->pixels = g_new (gfloat, (gsize) extent->width * extent->height * 4);
          gegl_buffer_get (buffer, extent, 1.0, format, pattern->pixels,
                           GEGL_AUTO_ROWSTRIDE, GEGL_ABYSS_NONE);
        }
      g_object_unref (buffer);
    }
}

static void
prepare (GeglOperation *operation)
{
  GeglProperties *o      = GEGL_PROPERTIES (operation);
  const Babl     *space  = gegl_operation_get_source_space (operation, "input");
  const Babl     *format = babl_format_with_space ("R'G'B'A float", space);

  gegl_operation_set_format (operation, "input",  format);
  gegl_operation_set_format (operation, "output", format);

  /* here, not in process(), which runs in several threads at once */
  load_pattern (o, format);
}

static gboolean
process (GeglOperation       *operation,
         void                *in_buf,
         void                *out_buf,
         glong                n_pixels,
         const GeglRectangle *roi,
         gint                 level)
{
  GeglProperties      *o       = GEGL_PROPERTIES (operation);
  Pattern             *pattern = o->user_data;
  const GeglRectangle *bounds;
  gfloat              *in      = in_buf;
  gfloat              *out     = out_buf;
  gdouble              factor  = 1 << level;
  gdouble              scale   = MAX (o->scale, 1.0) / 100.0;
  gdouble              ox, oy;
  gint                 x, y;

  if (! pattern || ! pattern->pixels)
    {
      /* no pattern (yet): leave the layer as it is */
      memcpy (out, in, n_pixels * 4 * sizeof (gfloat));
      return TRUE;
    }

  bounds = gegl_operation_source_get_bounding_box (operation, "input");
  ox = (bounds ? bounds->x : 0) + o->offset_x;
  oy = (bounds ? bounds->y : 0) + o->offset_y;

  x = roi->x;
  y = roi->y;

  while (n_pixels--)
    {
      gint    px = (gint) floor (((x + 0.5) * factor - ox) / scale);
      gint    py = (gint) floor (((y + 0.5) * factor - oy) / scale);
      gfloat *p;

      px %= pattern->width;
      py %= pattern->height;
      if (px < 0)
        px += pattern->width;
      if (py < 0)
        py += pattern->height;

      p = pattern->pixels + ((gsize) py * pattern->width + px) * 4;

      out[0] = p[0];
      out[1] = p[1];
      out[2] = p[2];
      out[3] = in[3] * p[3];

      in  += 4;
      out += 4;

      if (++x >= roi->x + roi->width)
        {
          x = roi->x;
          y++;
        }
    }

  return TRUE;
}

static void
finalize (GObject *object)
{
  GeglProperties *o = GEGL_PROPERTIES (object);

  pattern_free (o->user_data);
  o->user_data = NULL;

  G_OBJECT_CLASS (gegl_op_parent_class)->finalize (object);
}

static void
gegl_op_class_init (GeglOpClass *klass)
{
  GObjectClass                  *object_class    = G_OBJECT_CLASS (klass);
  GeglOperationClass            *operation_class = GEGL_OPERATION_CLASS (klass);
  GeglOperationPointFilterClass *point_class     = GEGL_OPERATION_POINT_FILTER_CLASS (klass);

  object_class->finalize   = finalize;
  operation_class->prepare = prepare;
  point_class->process     = process;

  gegl_operation_class_set_keys (operation_class,
    "name",        "gimphoto:pattern-overlay",
    "title",       _("Pattern Overlay"),
    "categories",  "light",
    "description", _("Photoshop's Pattern Overlay layer effect: an image "
                     "tiled where the layer has pixels"),
    NULL);
}

#endif
