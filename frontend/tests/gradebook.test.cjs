const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../templates/GV/gradebook.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
function setup() {
    const elements = {};
    const alerts = [];
    const input = { value: '8', disabled: false, focus() {} };
    const row = { id: 'row-10', querySelector: selector => selector === '.score-m1' ? input : null };
    const document = {
        getElementById(id) {
            return elements[id] ||= { value: '1', disabled: false, innerHTML: '',
                listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
        },
        querySelectorAll: selector => selector.endsWith('input') ? [input] : [row],
        addEventListener(type, fn) { this.ready = fn; }
    };
    const ctx = vm.createContext({ document, alert: text => alerts.push(text), console: { error() {} } });
    vm.runInContext(script, ctx);
    return { ctx, document, alerts, input, run: code => vm.runInContext(code, ctx) };
}
const result = (score = 8) => ({ ok: true, json: async () => ({ success: true,
    data: [{ MaNguoiDung: 10, HoTen: 'Student', M1: score }] }) });
test('changing any filter reloads and invalidates the old gradebook', () => {
    const s = setup();
    s.run('loadClasses = () => {}; let reloads = 0; loadData = () => { reloads++; };');
    s.document.ready();
    for (const id of ['class-select', 'subject-select', 'semester-select']) {
        s.run("loadedGradeContext = getGradeContext();");
        s.document.getElementById(id).listeners.change();
        assert.equal(s.run('loadedGradeContext'), null);
        assert.equal(s.document.getElementById('btn-save-grades').disabled, true);
    }
    assert.equal(s.run('reloads'), 3);
});
test('old subject rows cannot be saved under a newly selected subject', async () => {
    const s = setup();
    let calls = 0;
    s.ctx.fetch = async () => { calls++; return result(); };
    s.run('loadedGradeContext = getGradeContext();');
    s.document.getElementById('subject-select').value = '2';
    await s.ctx.saveAllGrades();
    assert.equal(calls, 0);
    assert.equal(s.alerts.length, 1);
});
test('out-of-order responses do not replace the latest subject', async () => {
    const s = setup();
    const pending = [];
    s.ctx.fetch = () => new Promise(resolve => pending.push(resolve));
    const old = s.ctx.loadGradebook();
    assert.equal(s.document.getElementById('btn-save-grades').disabled, true);
    s.document.getElementById('subject-select').value = '2';
    const latest = s.ctx.loadGradebook();
    pending[1](result(4));
    await latest;
    const rendered = s.document.getElementById('grade-body').innerHTML;
    pending[0](result(9));
    await old;
    assert.equal(s.document.getElementById('grade-body').innerHTML, rendered);
    assert.equal(s.run('loadedGradeContext'), '1:2:1');
});
test('saving uses loaded subject and semester and locks filters while pending', async () => {
    const s = setup();
    s.document.getElementById('subject-select').value = '2';
    s.document.getElementById('semester-select').value = '2';
    s.run('loadedGradeContext = getGradeContext();');
    let release;
    let payload;
    s.ctx.fetch = (url, opts) => {
        if (!opts) return Promise.resolve(result());
        payload = JSON.parse(opts.body);
        return new Promise(resolve => { release = resolve; });
    };
    const save = s.ctx.saveAllGrades();
    assert.equal(s.document.getElementById('subject-select').disabled, true);
    assert.equal(s.input.disabled, true);
    assert.deepEqual(payload, { student_id: 10, subject_id: 2, semester_id: 2, column_type: 'M1', grade: 8 });
    release({ ok: true, json: async () => ({ success: true }) });
    await save;
    assert.equal(s.document.getElementById('subject-select').disabled, false);
    assert.equal(s.input.disabled, false);
});
test('API failures are not reported as successful saves and preserve input', async () => {
    for (const ok of [false, true]) {
        const s = setup();
        s.run('loadedGradeContext = getGradeContext();');
        s.ctx.fetch = async () => ({ ok, json: async () => ({ success: false, message: 'Rejected' }) });
        await s.ctx.saveAllGrades();
        assert.equal(s.alerts.length, 1);
        assert.match(s.alerts[0], /0\/1/);
        assert.match(s.alerts[0], /Rejected/);
        assert.equal(s.input.value, '8');
        assert.equal(s.document.getElementById('btn-save-grades').disabled, false);
    }
});