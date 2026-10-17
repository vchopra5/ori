export class Timeline {
    constructor(command, input, label) {
        this.command = command;
        this.input = input;
        this.label = label;
        input.addEventListener('input', () => {
            command.goTo(Number(input.value));
            this.update();
        });
        this.update();
    }
    update() {
        const {instructions, cursor} = this.command;
        const n = instructions.length;
        this.input.disabled = this.command.busy || n === 0;
        this.input.min = String(this.command.first);
        this.input.max = String(n);
        this.input.value = String(cursor);
        this.label.textContent = `${cursor}/${n}`;
        this.label.title = instructions[cursor - 1] ?? '';
    }
}
