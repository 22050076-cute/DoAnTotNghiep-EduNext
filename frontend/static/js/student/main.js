import { fetchDashboardData } from './api.js';
import { renderUser, renderStats, renderTasks, renderBadges } from './ui.js';

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Cài đặt ngày tháng
    const today = new Date().toLocaleDateString('vi-VN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    document.getElementById('current-date').innerText = 'Hôm nay là ' + today;

    // 2. Lấy dữ liệu và hiển thị
    const data = await fetchDashboardData();
    if (data) {
        renderUser(data.user);
        renderStats(data.stats);
        renderTasks(data.tasks);
        renderBadges(data.badges);
    } else {
        document.getElementById('task-container').innerHTML = '<p class="text-red-500 p-4">Không thể tải dữ liệu.</p>';
    }

    // 3. Lắng nghe sự kiện tìm kiếm
    document.getElementById('search-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && e.target.value.trim() !== '') {
            alert(`Đang tìm kiếm: ${e.target.value}`);
        }
    });
});

// Xuất các hàm ra global để HTML (nút bấm) có thể gọi được
window.handleTaskClick = (id) => alert(`Chuyển đến làm bài tập ID: ${id}`);
window.joinOnlineClass = () => alert(`Đang kết nối vào Google Meet tiết học hiện tại...`);
window.showBadge = (name) => alert(`Thông tin huy hiệu: ${name}`);