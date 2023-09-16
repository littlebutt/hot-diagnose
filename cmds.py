import getopt
import os.path
import sys

from engine import Pipeline
from engine.manage import PluginManager
from logs import Logger


class Cmd:

    usage = '''
    Usages: hot-diagnose [OPTIONS] [OPTION_ARGS] [SOURCE_ARGS]
    
    Options:
    
        -s --source: The source file to execute. If the source file needs arguments, they can be append to the tail.
        -o --output: The path to the output file of the executing source file.
        -p --path:   The directory path that all files in the path will be rendered as output. If not provided, the
                     path to the source file will be set as default. Usually, it will also regard as PYTHONPATH.
        -h --help:   The help message.
    '''

    def parse(self):
        opts, args = getopt.getopt(sys.argv[1:],
                                   's:o:p:h',
                                   ['source=', 'output', 'path', 'help'])

        if any(opt in ['-h', '--help'] for opt, optarg in opts):
            print(self.usage)
            sys.exit()

        source = [optarg for opt, optarg in opts if opt in ['-s', '--source']]
        assert len(source) == 1
        source = source[0]

        PluginManager.load_plugins(['plugins'])

        if any(opt in ['-o', '--output'] for opt, optarg in opts):
            output = [optarg for opt, optarg in opts if opt in ['-o', '--output']]
            if len(output) > 1:
                raise RuntimeError("Cannot support multiple redirect output")
            PluginManager.enable_plugin('RedirectPlugin')
            redirect_plugin = PluginManager.get_plugin('RedirectPlugin')
            redirect_plugin.set_filename(output[0])

        if any(opt in ['-p', '--path'] for opt, optarg in opts):
            scope_paths = [optarg for opt, optarg in opts if opt in ['-p', '--path']]
        else:
            scope_paths = [source]

        scope_plugin = PluginManager.get_plugin('ScopePlugin')
        _funcs = []
        for path in scope_paths:
            if not os.path.isabs(path):
                path = os.path.abspath(path)
            sys.path.append(path)
            _funcs.append(lambda p: p.startswith(path))
        scope_plugin.set_scope_funcs(_funcs)

        source = [optarg for opt, optarg in opts if opt in ['-s', '--source']]
        assert len(source) == 1
        source = source[0]

        pipeline = Pipeline(source, args, scope_paths[0])
        pipeline.run()