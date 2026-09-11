export function renderUser(user) {
    document.getElementById('user-avatar').src = user.avatar;
    document.getElementById('user-fullname').innerText = user.name;
    document.getElementById('user-firstname').innerText = user.first_name;
    document.getElementById('user-class').innerText = user.class_name;
    document.getElementById('current-period').innerText = user.current_period;
    document.getElementById('today-alert').innerHTML = user.today_alert;
}

export function renderStats(stats) {
    document.getElementById('total-xp').innerText = stats.total_xp;
    // Delay 1 chút để tạo hiệu ứng chạy thanh % mượt mà
    setTimeout(() => {
        document.getElementById('progress-text').innerText = stats.learning_progress + '%';
        document.getElementById('progress-bar').style.width = stats.learning_progress + '%';
    }, 100);
}

export function renderTasks(tasks) {
    const container = document.getElementById('task-container');
    document.getElementById('nav-task-count').innerText = tasks.length;
    container.innerHTML = ''; 

    tasks.forEach(task => {
        const isOverdue = task.status === 'Quá hạn';
        const btnClass = isOverdue 
            ? 'bg-slate-900 text-white hover:bg-rose-600' 
            : `bg-white border-2 border-slate-200 text-slate-700 hover:border-${task.color}-500 hover:text-${task.color}-600`;

        const html = `
            <div class="group bg-white flex flex-col sm:flex-row items-center justify-between p-5 rounded-2xl border border-slate-200 shadow-sm gap-4">
                <div class="flex items-center gap-4 w-full sm:w-auto">
                    <div class="w-12 h-12 rounded-full bg-${task.color}-50 flex items-center justify-center shrink-0">
                        <i class="ph-fill ${task.icon} text-2xl text-${task.color}-500"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                            <h4 class="font-bold text-slate-800 text-base">${task.title}</h4>
                            ${isOverdue ? `<span class="bg-rose-100 text-rose-600 text-[10px] font-extrabold px-2 py-0.5 rounded uppercase">Quá hạn</span>` : ''}
                        </div>
                        <p class="text-sm text-slate-500 font-medium flex items-center gap-1.5">
                            <i class="ph-bold ph-clock"></i> Hạn chót: ${task.deadline}
                        </p>
                    </div>
                </div>
                <button onclick="window.handleTaskClick(${task.id})" class="w-full sm:w-auto px-5 py-2.5 text-sm font-bold rounded-xl transition-all ${btnClass}">
                    ${task.action_text}
                </button>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', html);
    });
}

export function renderBadges(badges) {
    const container = document.getElementById('badges-container');
    container.innerHTML = '';
    
    badges.forEach(badge => {
        const isLocked = badge.locked;
        const wrapperClass = isLocked ? 'opacity-50 grayscale' : 'cursor-pointer hover:scale-110';
        const bgClass = isLocked ? 'bg-slate-100' : `bg-gradient-to-br from-${badge.color}-100 to-${badge.color}-200 border-${badge.color}-200`;
        
        const html = `
            <div class="flex flex-col items-center group transition-transform duration-300 ${wrapperClass}" onclick="window.showBadge('${badge.name}')">
                <div class="w-16 h-16 ${bgClass} rounded-full flex items-center justify-center mb-2 shadow-sm border relative">
                    <span class="text-3xl drop-shadow-md">${badge.icon}</span>
                    ${badge.multiplier ? `<div class="absolute -top-1 -right-1 w-5 h-5 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-white shadow-sm">${badge.multiplier}</div>` : ''}
                    ${isLocked ? `<i class="ph-fill ph-lock-key absolute text-slate-400 text-lg bg-white rounded-full"></i>` : ''}
                </div>
                <span class="text-[11px] font-bold text-slate-700 text-center">${badge.name}</span>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', html);
    });
}