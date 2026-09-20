const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../templates/GV/dashboard_teacher.html'), 'utf8');
for (const subject of [{ id: 6, name: 'Tin hoc' }, { MaMonHoc: 6, TenMonHoc: 'Tin hoc' }]) {
    test('subject dropdown accepts API fields ' + Object.keys(subject).join(','), async () => {
        const select = { options: [], replaceChildren(...options) { this.options = options; } };
        const context = vm.createContext({
            document: {
                addEventListener() {},
                getElementById() { return select; },
                createElement() { return { get text() { return this.textContent; } }; }
            },
            fetch: async () => ({ ok: true, json: async () => ({ success: true, data: [subject] }) }),
            console
        });
        vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
        await context.loadTeacherSubjects();
        assert.equal(select.options.length, 1);
        assert.equal(select.options[0].value, '6');
        assert.equal(select.options[0].textContent, 'Tin hoc');
    });
}