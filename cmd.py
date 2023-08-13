import getopt
import os
import sys

from engine import Pipeline


class Cmd:

    usage = '''
    -s --source: the source script file
    -r --redirect: redirect path for source file output
    -h --help: help message
    '''

    def parse(self):
        opts, args = getopt.getopt(sys.argv[1:], 's:drh', ['source=', 'display', 'redirect', 'help'])

        if any(opt in ['-h', '--help'] for opt, optarg in opts):
            print(self.usage)
            sys.exit()

        source = [optarg for opt, optarg in opts if opt in ['-s', '--source']]

        pipeline = Pipeline(source, args, os.getcwd(), None)
        pipeline.run()