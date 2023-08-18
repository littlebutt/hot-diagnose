from cmds import Cmd

from plugins.redirect import RedirectPlugin


if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # 过滤自身脚本
    # 指定模块运行