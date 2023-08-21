from cmds import Cmd

from plugins.redirect import RedirectPlugin

if __name__ == '__main__':
    cmd = Cmd()
    cmd.parse()
    # server端消费者
