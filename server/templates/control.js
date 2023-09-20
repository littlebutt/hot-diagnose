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
        return this.queue.shift()
    }

    _blink_line(classname) {
        let target = document.getElementsByClassName(classname)[0]
        let bgc = target.style.backgroundColor
        let rgb = bgc.replace(/^rgba?\(|\s+|\)$/g,'').split(',');
        window.scrollTo(0, target.offsetTop - 500)
        gsap.to(target, {scale: 2})
        gsap.to(target, {scale: 1, backgroundColor: `rgb(255, ${rgb[1] - 10}, ${rgb[2] - 10})`})
    }

    do_start() {
        const render = () => {
            let data = this.peak()
            console.log(data)
            window.ctrl._blink_line(data.classname)
        }
        this.send('start')
        this.timmer = setInterval(render, 500)
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