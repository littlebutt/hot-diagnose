import getopt
import os.path
import sys

from engine import Pipeline
from engine.manage import PluginManager
from logs import Logger


class Cmd:

    usage = '''
    Usages: hot-cov [OPTIONS] [OPTION_ARGS] FILENAME [ARGS]
    
    Options:
    
        -s --source: the source script file
        -o --output: redirect path for source file output
        -p --path: specify a path that all files in the path should be included. 
                   It is necessary if the source is in a package
        -h --help: help message
    '''

    def parse(self):
        opts, args = getopt.getopt(sys.argv[1:],
                                   's:o:p:h',
                                   ['source=', 'output', 'path', 'help'])

        if any(opt in ['-h', '--help'] for opt, optarg in opts):
            print(self.usage)
            sys.exit()

        PluginManager.load_plugins(['plugins'])

        if any(opt in ['-o', '--output'] for opt, optarg in opts):
            output = [optarg for opt, optarg in opts if opt in ['-o', '--output']]
            if len(output) > 1:
                raise RuntimeError("Cannot support multiple redirect output")
            PluginManager.enable_plugin('RedirectPlugin')
            redirect_plugin = PluginManager.get_plugin('RedirectPlugin')
            assert redirect_plugin is not None
            redirect_plugin.set_filename(output[0])

        scope_paths = None
        if any(opt in ['-p', '--path'] for opt, optarg in opts):
            scope_paths = [optarg for opt, optarg in opts if opt in ['-p', '--path']]
            scope_plugin = PluginManager.get_plugin('ScopePlugin')
            assert scope_plugin is not None
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

        scope_path = None
        if scope_paths is not None:
            if len(scope_paths) > 1:
                Logger.get_logger('cmds').warning("Only support single scope path")
            scope_path = scope_paths[0]
        pipeline = Pipeline(source, args, scope_path)
        pipeline.run()