"""GDB command: render-dump FILE [RENDER_GLOBALS_POINTER_EXPRESSION].

Read-only WC3 render submissions, with no inferior function calls. Use symbols
from the exact running build. Source this file inside GDB, then detach promptly.
"""
import json
import gdb


def vector(value):
    return [float(value[axis]) for axis in ('x', 'y', 'z')]


def model_info(pointer, paths):
    model = pointer.dereference()
    result = {'address': str(pointer), 'path': paths.get(int(pointer)),
              'type': int(model['modeltype'])}
    if not int(model['mdx']):
        return result
    mdx = model['mdx'].dereference()
    count = int(mdx['num_sequences'])
    if not 0 <= count <= 4096:
        raise gdb.GdbError('Invalid sequence count; check matching build symbols')
    result['name'] = mdx['info']['name'].string()
    result['sequences'] = [
        {'name': mdx['sequences'][i]['name'].string(),
         'interval': [int(mdx['sequences'][i]['interval'][j]) for j in (0, 1)]}
        for i in range(count)]
    return result


class RenderDump(gdb.Command):
    def __init__(self):
        super().__init__('render-dump', gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        args = gdb.string_to_argv(arg)
        if not 1 <= len(args) <= 2:
            raise gdb.GdbError('Usage: render-dump FILE [RENDER_GLOBALS_POINTER_EXPRESSION]')
        root = gdb.parse_and_eval(args[1] if len(args) == 2 else '&tr').dereference()
        view = root['viewDef']
        count = int(view['num_entities'])
        if not 0 <= count <= 16384:
            raise gdb.GdbError('Invalid entity count; check matching build symbols')
        paths, warnings = {}, []
        try:
            registry = gdb.parse_and_eval('mod_known')
            lo, hi = registry.type.range()
            for i in range(lo, hi + 1):
                if int(registry[i]['model']):
                    paths[int(registry[i]['model'])] = registry[i]['name'].string()
        except gdb.error as error:
            warnings.append('Model path registry unavailable: ' + str(error))
        entities, models = [], {}
        for i in range(count):
            entity = view['entities'][i]
            pointer = entity['model']
            key = str(pointer)
            if int(pointer) and key not in models:
                models[key] = model_info(pointer, paths)
            entities.append({
                'submission': i, 'number': int(entity['number']), 'model': key,
                'origin': vector(entity['origin']), 'frame': int(entity['frame']),
                'oldframe': int(entity['oldframe']), 'flags': int(entity['flags']),
                'angle': float(entity['angle']), 'scale': float(entity['scale']),
                'team': int(entity['team'])})
        camera = view['camerastate'][0]
        output = {'schema': 1, 'pid': gdb.selected_inferior().pid,
                  'time': int(view['time']), 'lerpfrac': float(view['lerpfrac']),
                  'camera': {'origin': vector(camera['origin']), 'eye': vector(camera['eye']),
                             'angles': vector(camera['viewangles']),
                             'distance': float(camera['distance']), 'fov': float(camera['fov'])},
                  'models': models, 'entities': entities, 'warnings': warnings}
        with open(args[0], 'w') as stream:
            json.dump(output, stream, indent=2, allow_nan=False)
        gdb.write('Wrote %d submissions, %d models to %s\n' % (count, len(models), args[0]))
        for warning in warnings:
            gdb.write(warning + '\n', gdb.STDERR)


RenderDump()
