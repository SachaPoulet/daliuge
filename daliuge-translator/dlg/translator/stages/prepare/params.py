#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2015
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#

import json
import string
import logging

from dlg.translator.stages.prepare.config import fill_config

logger = logging.getLogger(f"dlg.{__name__}")


class _LGTemplate(string.Template):
    delimiter = "~"
    idpattern = r"[_a-z][_a-z0-9\.]*"


def _flatten_dict(d):
    flat = dict(d)
    for key, value in d.items():
        if isinstance(value, dict):
            flattened = _flatten_dict(value)
            flat.update({"%s.%s" % (key, k): v for k, v in flattened.items()})
        else:
            flat[key] = value
    return flat


def fill(lg, params):
    """Logical Graph + params -> Filled Logical Graph"""
    logger.info("Filling Logical Graph with parameters: %r", params)
    flat_params = _flatten_dict(params)
    if hasattr(lg, "read"):
        lg = lg.read()
    elif not isinstance(lg, str):
        lg = json.dumps(lg)
    lg = _LGTemplate(lg).substitute(flat_params)
    return json.loads(lg)


def apply_config(lg: str, config: dict):
    """
    Give a logical graph, fill the
    :param lg:
    :param config:
    :return:
    """
    logger.info("Applying configuration to Logical Graph...")
    return fill_config(lg, config)
