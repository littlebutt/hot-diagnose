import getopt
import os
import sys

from engine import Pipeline
from plugins import RedirectPlugin


class Cmd:

    usage = '''
    -s --source: the source script file
    -o --output: redirect path for source file output
    -h --help: help message
    '''

    def parse(self):
        opts, args = getopt.getopt(sys.argv[1:], 's:doh', ['source=', 'display', 'output', 'help'])

        if any(opt in ['-h', '--help'] for opt, optarg in opts):
            print(self.usage)
            sys.exit()

        if any(opt in ['-o', '--output'] for opt, optarg in opts):
            output = [optarg for opt, optarg in opts if opt in opts]
            if len(output) > 1:
                raise RuntimeError("Cannot support multiple redirect output")
            Pipeline.enable_plugin(RedirectPlugin)
            redirect_plugin: RedirectPlugin = Pipeline.get_plugin(RedirectPlugin)
            assert redirect_plugin is not None
            redirect_plugin.set_out(output[0])



        source = [optarg for opt, optarg in opts if opt in ['-s', '--source']]

        pipeline = Pipeline(source, args, None)
        pipeline.run()