export async function fetchDashboardData() {
    try {
        const response = await fetch('/api/student/dashboard');
        const result = await response.json();
        if (result.success) return result.data;
        return null;
    } catch (error) {
        console.error("Lỗi API:", error);
        return null;
    }
}