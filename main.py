from cmds import Cmd

from plugins.redirect import RedirectPlugin


if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # debug log等级
    # 过滤自身脚本
    # 指定模块运行