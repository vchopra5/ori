export class CommandArea {
    constructor(command, textarea) {
        this.textarea = textarea;
        this.textarea.addEventListener('keydown', this.keydown.bind(this));
        this.command = command;
        command.commandArea = this;
    }

    addLine(text) {
        const value = this.textarea.value;
        const lastLineStart = value.lastIndexOf('\n') + 1;
        const lastLine = value.substring(lastLineStart).trim();
        if (lastLine === text) {
            // Only a new line
            this.textarea.value += `\n`;
        } else {
            // Insert at the end
            this.textarea.value += `${text}\n`;
        }
        // Scroll to the end
        this.textarea.selectionStart = this.textarea.selectionEnd = this.textarea.value.length;
        this.textarea.focus();
    }

    keydown = function (e) {
        const el = e.target; // HTMLTextAreaElement
        if (e.key === 'Enter') {
            e.preventDefault();
            if (this.command.animating) return;
            const caretPos = el.selectionStart;
            const value = el.value;
            const start = value.lastIndexOf('\n', caretPos - 1) + 1;
            let end = value.indexOf('\n', caretPos);
            if (end === -1) {
                end = value.length;
            }
            const line = value.substring(start, end);
            this.command.command(line);
            this.textarea.selectionStart = this.textarea.selectionEnd = this.textarea.value.length;
            el.scrollTop = el.scrollHeight;
        }
        const key = e.key.toLowerCase();
        if ((e.ctrlKey || e.metaKey) && (key === 'z' || key === 'y')) {
            e.preventDefault();
            e.stopPropagation();
            this.command.command(key === 'y' || e.shiftKey ? 'redo' : 'undo');
        }
    }
}
