import sys
from cmd import Cmd

from engine.run import PyRunner
from engine.tracer import Tracer

if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # 输出重定向
    # 过滤自身脚本
    # filename拼接
    # 指定模块运行