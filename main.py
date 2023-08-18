from cmds import Cmd

from plugins.redirect import RedirectPlugin

if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # 指定模块运行
    # 消息队列 <order filename lineno ctx>
    # server端消费者
