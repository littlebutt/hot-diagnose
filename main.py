from cmds import Cmd

from plugins.redirect import RedirectPlugin

if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # message queue 双向队列
    # server端消费者
