"""Check the prepared Python spec against Carrot's navigation wire layout."""
import argparse
from pathlib import Path
import sys


def check(checkout):
    sys.path.insert(0, str(checkout))
    from jetlink.spec import ModelSpec
    inputs = {'new_img': (2, 6, 128, 256), 'desire': (1, 8),
              'traffic_convention': (1, 2), 'action_t': (1, 2)}
    outputs = {'outputs': (1, 18580)}
    base = ModelSpec('', 0, 4, inputs, outputs, {}, None)
    if base.packed_nbytes != 48:
        raise ValueError('Non-navigation model wire layout changed')
    for shape in ((47,), (1, 47)):
        nav = ModelSpec('', 0, 4, {**inputs, 'navigation': shape, 'nav_map': (1, 1, 256, 256)}, outputs, {}, None)
        expected = ['desire', 'traffic_convention', 'action_t', 'nav_map', 'navigation']
        if list(nav.packed_shapes) != expected or nav.packed_nbytes != 262380:
            raise ValueError('Carrot navigation wire order/length does not match')
        if nav.infer_req_nbytes - base.infer_req_nbytes != 262332:
            raise ValueError('Navigation request byte count does not match')
        if nav.packed_layout['navigation'][0] != slice(65548, 65595):
            raise ValueError('Navigation instruction offset does not match')
    print('Carrot navigation and original-model wire contracts passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('checkout', type=Path)
    check(parser.parse_args().checkout.resolve())
