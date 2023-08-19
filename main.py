from cmds import Cmd

from plugins.redirect import RedirectPlugin

if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # 消息队列 <order filename lineno ctx>
    # file system
    # server端消费者
