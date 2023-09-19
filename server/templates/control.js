class Controller {
    constructor(hostname, port) {
        this.queue = []
        this.ws = new WebSocket(`ws://${hostname}:${port}`)
        this.ws.onmessage = function (message) {
            window.ctrl.queue.push(JSON.parse(message.data))
        }
    }

    send(message) {
        this.ws.send(message)
    }

    peak() {
        return this.queue.pop()
    }

    do_start() {
        const render = () => {
            let data = this.peak()
            console.log(data)
            document.getElementsByClassName(data.classname)[0].innerHTML = '+'
        }
        this.send('start')
        this.timmer = setInterval(render, 1000)
    }

    do_stop() {
        clearInterval(this.timmer)
    }
}

window.onload = () => {
    window.ctrl = new Controller('localhost', 8765)
    let control = document.querySelector('#control')
    control.innerHTML = 'START'
    control.onclick = () => {
        if (control.innerHTML === 'START') {
            control.innerHTML = 'STOP'
            window.ctrl.do_start()
        } else {
            control.innerHTML = 'START'
            window.ctrl.do_stop()
        }
    }
}