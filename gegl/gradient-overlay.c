/* gimphoto:gradient-overlay: Photoshop's Gradient Overlay layer effect.
 *
 * Paints a two-colour gradient where the input has pixels, keeping the
 * input's alpha (as Photoshop's overlay effects do); the layer filter's
 * own blend mode and opacity mix it with the layer. The gradient is laid
 * out on the input's bounding box, as Photoshop's "Align with Layer".
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

enum_start (gimphoto_gradient_overlay_style)
  enum_value (GIMPHOTO_GRADIENT_LINEAR,    "linear",    N_("Linear"))
  enum_value (GIMPHOTO_GRADIENT_RADIAL,    "radial",    N_("Radial"))
  enum_value (GIMPHOTO_GRADIENT_ANGLE,     "angle",     N_("Angle"))
  enum_value (GIMPHOTO_GRADIENT_REFLECTED, "reflected", N_("Reflected"))
  enum_value (GIMPHOTO_GRADIENT_DIAMOND,   "diamond",   N_("Diamond"))
enum_end (GimphotoGradientOverlayStyle)

property_color (color1, _("Start color"), "black")
property_color (color2, _("End color"), "white")

property_enum (style, _("Style"),
               GimphotoGradientOverlayStyle, gimphoto_gradient_overlay_style,
               GIMPHOTO_GRADIENT_LINEAR)

property_double (angle, _("Angle"), 90.0)
  description (_("Direction from the start colour to the end colour; 90 is upwards"))
  value_range (-360.0, 360.0)
  ui_meta ("unit", "degree")

property_double (scale, _("Scale"), 100.0)
  description (_("Size of the gradient, in percent of the layer"))
  value_range (10.0, 150.0)

property_boolean (reverse, _("Reverse"), FALSE)

property_double (offset_x, _("Horizontal offset"), 0.0)
  description (_("Centre of the gradient, in percent of the layer's width"))
  value_range (-100.0, 100.0)

property_double (offset_y, _("Vertical offset"), 0.0)
  description (_("Centre of the gradient, in percent of the layer's height"))
  value_range (-100.0, 100.0)

#else

#define GEGL_OP_POINT_FILTER
#define GEGL_OP_NAME     gradient_overlay
#define GEGL_OP_C_SOURCE gradient-overlay.c

#include "gegl-op.h"

static void
prepare (GeglOperation *operation)
{
  const Babl *space  = gegl_operation_get_source_space (operation, "input");
  const Babl *format = babl_format_with_space ("R'G'B'A float", space);

  gegl_operation_set_format (operation, "input",  format);
  gegl_operation_set_format (operation, "output", format);
}

/* Position along the gradient, 0 (start colour) to 1 (end colour). */
static gdouble
gradient_position (GimphotoGradientOverlayStyle style,
                   gdouble                      u,
                   gdouble                      v,
                   gdouble                      length,
                   gdouble                      radius)
{
  gdouble t;

  switch (style)
    {
    case GIMPHOTO_GRADIENT_RADIAL:
      t = sqrt (u * u + v * v) / radius;
      break;

    case GIMPHOTO_GRADIENT_ANGLE:
      t = atan2 (v, u) / (2.0 * G_PI);
      if (t < 0.0)
        t += 1.0;
      break;

    case GIMPHOTO_GRADIENT_REFLECTED:
      t = fabs (u) / (length / 2.0);
      break;

    case GIMPHOTO_GRADIENT_DIAMOND:
      t = (fabs (u) + fabs (v)) / radius;
      break;

    case GIMPHOTO_GRADIENT_LINEAR:
    default:
      t = 0.5 + u / length;
      break;
    }

  return CLAMP (t, 0.0, 1.0);
}

static gboolean
process (GeglOperation       *operation,
         void                *in_buf,
         void                *out_buf,
         glong                n_pixels,
         const GeglRectangle *roi,
         gint                 level)
{
  GeglProperties      *o      = GEGL_PROPERTIES (operation);
  const Babl          *format = gegl_operation_get_format (operation, "output");
  const GeglRectangle *bounds;
  gfloat              *in     = in_buf;
  gfloat              *out    = out_buf;
  gfloat               start[4];
  gfloat               end[4];
  gdouble              w, h, cx, cy, dx, dy, length, radius, scale, factor;
  gint                 x, y;

  gegl_color_get_pixel (o->reverse ? o->color2 : o->color1, format, start);
  gegl_color_get_pixel (o->reverse ? o->color1 : o->color2, format, end);

  bounds = gegl_operation_source_get_bounding_box (operation, "input");
  if (! bounds || bounds->width < 1 || bounds->height < 1)
    bounds = roi;

  /* work in full-resolution coordinates at any zoom level */
  factor = 1 << level;
  w      = MAX (bounds->width, 1) ;
  h      = MAX (bounds->height, 1);
  cx     = bounds->x + w / 2.0 + o->offset_x / 100.0 * w;
  cy     = bounds->y + h / 2.0 + o->offset_y / 100.0 * h;
  dx     = cos (o->angle * G_PI / 180.0);
  dy     = -sin (o->angle * G_PI / 180.0);
  scale  = MAX (o->scale, 1.0) / 100.0;
  /* linear: the layer's extent along the direction; radial and diamond:
   * half its diagonal */
  length = MAX ((fabs (w * dx) + fabs (h * dy)) * scale, 1.0);
  radius = MAX (0.5 * sqrt (w * w + h * h) * scale, 1.0);

  x = roi->x;
  y = roi->y;

  while (n_pixels--)
    {
      gdouble px = (x + 0.5) * factor - cx;
      gdouble py = (y + 0.5) * factor - cy;
      gdouble u  = px * dx + py * dy;
      gdouble v  = -px * dy + py * dx;
      gdouble t  = gradient_position (o->style, u, v, length, radius);
      gint    c;

      for (c = 0; c < 3; c++)
        out[c] = start[c] + (end[c] - start[c]) * t;
      out[3] = in[3] * (start[3] + (end[3] - start[3]) * t);

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
gegl_op_class_init (GeglOpClass *klass)
{
  GeglOperationClass            *operation_class = GEGL_OPERATION_CLASS (klass);
  GeglOperationPointFilterClass *point_class     = GEGL_OPERATION_POINT_FILTER_CLASS (klass);

  operation_class->prepare = prepare;
  point_class->process     = process;

  gegl_operation_class_set_keys (operation_class,
    "name",        "gimphoto:gradient-overlay",
    "title",       _("Gradient Overlay"),
    "categories",  "light",
    "description", _("Photoshop's Gradient Overlay layer effect: a gradient "
                     "where the layer has pixels"),
    NULL);
}

#endif
