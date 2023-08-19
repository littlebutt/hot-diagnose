import getopt
import os.path
import sys

from engine import Pipeline
from plugins import RedirectPlugin
from plugins import ScopePlugin
from queues import MessageQueue


class Cmd:

    usage = '''
    Usages: hot-cov [OPTIONS] [OPTION_ARGS] FILENAME [ARGS]
    
    Options:
    
        -s --source: the source script file
        -o --output: redirect path for source file output
        -d --display: specify the display manner, default html
        -p --path: specify a path that all files in the path should be included. 
                   It is necessary if the source is in a package
        -h --help: help message
    '''

    def parse(self):
        opts, args = getopt.getopt(sys.argv[1:], 's:d:o:p:h', ['source=', 'display', 'output', 'path', 'help'])

        if any(opt in ['-h', '--help'] for opt, optarg in opts):
            print(self.usage)
            sys.exit()

        if any(opt in ['-o', '--output'] for opt, optarg in opts):
            output = [optarg for opt, optarg in opts if opt in ['-o', '--output']]
            if len(output) > 1:
                raise RuntimeError("Cannot support multiple redirect output")
            Pipeline.enable_plugin('RedirectPlugin')
            redirect_plugin: RedirectPlugin = Pipeline.get_plugin('RedirectPlugin')
            assert redirect_plugin is not None
            redirect_plugin.set_out(output[0])

        if any(opt in ['-p', '--path'] for opt, optarg in opts):
            paths = [optarg for opt, optarg in opts if opt in ['-p', '--path']]
            scope_plugin: ScopePlugin = Pipeline.get_plugin('ScopePlugin')
            assert scope_plugin is not None
            _funcs = []
            for path in paths:
                if not os.path.isabs(path):
                    path = os.path.abspath(path)
                sys.path.append(path)
                _funcs.append(lambda p: p.startswith(path))
            scope_plugin.set_scope_funcs(_funcs)

        source = [optarg for opt, optarg in opts if opt in ['-s', '--source']]

        message_queue = MessageQueue()
        pipeline = Pipeline(source, args, message_queue)
        pipeline.run()