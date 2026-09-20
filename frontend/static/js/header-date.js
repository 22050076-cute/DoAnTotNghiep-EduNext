(() => {
    const formatter = new Intl.DateTimeFormat('vi-VN', {
        timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: 'numeric', month: 'numeric', year: 'numeric'
    });
    function updateHeaderDate() {
        const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(part => [part.type, part.value]));
        const weekday = parts.weekday.charAt(0).toUpperCase() + parts.weekday.slice(1);
        document.querySelectorAll('[data-header-date]').forEach(element => {
            element.textContent = `${weekday}, ${parts.day} Tháng ${parts.month}, ${parts.year}`;
            element.setAttribute('datetime', `${parts.year}-${parts.month.padStart(2, '0')}-${parts.day.padStart(2, '0')}`);
        });
    }
    updateHeaderDate();
    setInterval(updateHeaderDate, 1000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateHeaderDate();
    });
})();
