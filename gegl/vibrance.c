/* gimphoto:vibrance: Photoshop's Vibrance adjustment.
 *
 * Vibrance raises (or lowers) saturation more where colours are dull than
 * where they are already saturated, and spares skin tones, so a photo gets
 * livelier without people turning orange; greys stay grey. Saturation is
 * the plain, uniform slider next to it, as in Photoshop's dialog.
 *
 * Each pixel moves away from (or towards) its grey of the same luma:
 *
 *   out = luma + (in - luma) * (1 + vibrance * (1 - s) * skin) * (1 + saturation)
 *
 * s is the pixel's HSV saturation (0 grey, 1 pure colour) and skin is 1,
 * or less for hues and saturations typical of skin when skin protection is
 * on and vibrance is raised. It works on gamma-encoded values, as
 * Photoshop does. (GEGL's own gegl:vibrance has the two sliders but no
 * skin protection.)
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

property_double (vibrance, _("Vibrance"), 0.0)
  description (_("Saturation added (or removed) mostly where colours are dull, sparing skin tones"))
  value_range (-100.0, 100.0)

property_double (saturation, _("Saturation"), 0.0)
  description (_("Saturation added (or removed) evenly to every colour"))
  value_range (-100.0, 100.0)

property_boolean (protect_skin, _("Protect skin tones"), TRUE)
  description (_("Raise skin tones less than other colours when vibrance is raised"))

#else

#define GEGL_OP_POINT_FILTER
/* GEGL has its own gegl:vibrance (no skin protection): the type name must differ */
#define GEGL_OP_NAME     gimphoto_vibrance
#define GEGL_OP_C_SOURCE vibrance.c

#include "gegl-op.h"

/* How much vibrance skin tones keep with protection on (Photoshop keeps
 * them close to unchanged). */
#define SKIN_KEEP 0.3

static void
prepare (GeglOperation *operation)
{
  const Babl *space  = gegl_operation_get_source_space (operation, "input");
  const Babl *format = babl_format_with_space ("R'G'B'A float", space);

  gegl_operation_set_format (operation, "input",  format);
  gegl_operation_set_format (operation, "output", format);
}

static gfloat
smoothstep (gfloat edge0,
            gfloat edge1,
            gfloat x)
{
  gfloat t = CLAMP ((x - edge0) / (edge1 - edge0), 0.0f, 1.0f);

  return t * t * (3.0f - 2.0f * t);
}

/* 1 for a colour that looks like skin (orange-red hues from about 5 to 45
 * degrees, moderately saturated), falling to 0 away from it. */
static gfloat
skin_likeness (gfloat r,
               gfloat g,
               gfloat b,
               gfloat max,
               gfloat chroma,
               gfloat sat)
{
  gfloat hue;

  if (chroma <= 0.0f || max != r)
    return 0.0f;  /* skin is red-dominant */

  hue = 60.0f * (g - b) / chroma;   /* -60 .. 60 degrees around red */

  return smoothstep (-10.0f, 5.0f, hue) * (1.0f - smoothstep (40.0f, 55.0f, hue)) *
         smoothstep (0.08f, 0.18f, sat) * (1.0f - smoothstep (0.6f, 0.8f, sat));
}

static gboolean
process (GeglOperation       *operation,
         void                *in_buf,
         void                *out_buf,
         glong                n_pixels,
         const GeglRectangle *roi,
         gint                 level)
{
  GeglProperties *o          = GEGL_PROPERTIES (operation);
  const gfloat    vibrance   = o->vibrance / 100.0;
  const gfloat    saturation = 1.0f + o->saturation / 100.0;
  gfloat         *in         = in_buf;
  gfloat         *out        = out_buf;

  while (n_pixels--)
    {
      gfloat r      = in[0];
      gfloat g      = in[1];
      gfloat b      = in[2];
      gfloat max    = MAX (r, MAX (g, b));
      gfloat min    = MIN (r, MIN (g, b));
      gfloat chroma = max - min;
      gfloat sat    = max > 0.0f ? CLAMP (chroma / max, 0.0f, 1.0f) : 0.0f;
      gfloat luma   = 0.2126f * r + 0.7152f * g + 0.0722f * b;
      gfloat amount = vibrance * (1.0f - sat);
      gfloat factor;
      gint   c;

      if (o->protect_skin && amount > 0.0f)
        amount *= 1.0f - (1.0f - SKIN_KEEP) * skin_likeness (r, g, b, max, chroma, sat);

      factor = MAX (0.0f, (1.0f + amount) * saturation);

      /* not clamped: high bit depth images keep values above 1, as with
       * GEGL's own saturation */
      for (c = 0; c < 3; c++)
        out[c] = luma + (in[c] - luma) * factor;
      out[3] = in[3];

      in  += 4;
      out += 4;
    }

  return TRUE;
}

static void
gegl_op_class_init (GeglOpClass *klass)
{
  GeglOperationClass            *operation_class = GEGL_OPERATION_CLASS (klass);
  GeglOperationPointFilterClass *point_class     = GEGL_OPERATION_POINT_FILTER_CLASS (klass);

  operation_class->prepare = prepare;
  point_class->process     = process;

  gegl_operation_class_set_keys (operation_class,
    "name",        "gimphoto:vibrance",
    "title",       _("Vibrance"),
    "categories",  "color",
    "description", _("Photoshop's Vibrance: more saturation where colours are "
                     "dull, sparing skin tones, and plain Saturation"),
    NULL);
}

#endif
