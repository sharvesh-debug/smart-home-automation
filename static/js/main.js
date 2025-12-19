// static/js/main.js
// The definitive, final, and complete JavaScript for the HTTP polling-based smart home dashboard.

document.addEventListener('DOMContentLoaded', () => {
    // --- UI Elements ---
    const body = document.body;
    const themeToggle = document.getElementById('theme-toggle');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    // --- Main Polling Function ---
    // This function is the heart of the live updates. It fetches data from the server every few seconds.
    async function fetchUpdates() {
        try {
            // Fetch environment and notification/security data simultaneously for speed.
            const [envResponse, notifResponse] = await Promise.all([
                fetch('/api/environment'),
                fetch('/api/notifications')
            ]);

            if (envResponse.ok) {
                const data = await envResponse.json();
                updateEnvironmentUI(data);
            } else {
                console.error("Failed to fetch environment data.");
            }

            if (notifResponse.ok) {
                const data = await notifResponse.json();
                updateNotificationsUI(data);
            } else {
                console.error("Failed to fetch notification data.");
            }
        } catch (error) {
            console.error("Error during update fetch:", error);
        }
    }

    // --- UI Update Functions ---

    function updateEnvironmentUI(data) {
        // This function updates the main dashboard environment card.
        if (!data || Object.keys(data).length === 0) return; // Don't update if data is empty

        const tempValue = document.getElementById('temp-value');
        const humidityValue = document.getElementById('humidity-value');
        const rainProgress = document.getElementById('rain-progress');
        const rainChanceValue = document.getElementById('rain-chance-value');
        const weatherStatus = document.getElementById('weather-status');
        const weatherIcon = document.getElementById('weather-icon');

        if (tempValue) tempValue.textContent = `${data.temp}°C`;
        if (humidityValue) humidityValue.textContent = `${data.humidity}%`;
        if (rainProgress) rainProgress.style.width = `${data.rain_chance}%`;
        if (rainChanceValue) rainChanceValue.textContent = `${data.rain_chance}%`;
        if (weatherStatus) weatherStatus.textContent = data.status;

        if (weatherIcon) {
            // Update weather icon based on the live status
            if (data.is_raining) {
                weatherIcon.className = 'fas fa-cloud-showers-heavy';
            } else if (data.status.toLowerCase().includes('cloud')) {
                weatherIcon.className = 'fas fa-cloud';
            } else if (data.status.toLowerCase().includes('sun') || data.status.toLowerCase().includes('clear')) {
                weatherIcon.className = 'fas fa-sun';
            } else if (data.status.toLowerCase().includes('thunderstorm')) {
                weatherIcon.className = 'fas fa-bolt';
            } else {
                weatherIcon.className = 'fas fa-smog'; // Default for mist, haze etc.
            }
        }
    }

    function updateNotificationsUI(data) {
        // This function handles the notification badge and the security permission request.

        // 1. Update the badge count in the top bar
        const notificationBadge = document.getElementById('notification-badge');
        if (notificationBadge && typeof data.unread_count !== 'undefined') {
            // Force update the badge text and visibility
            notificationBadge.textContent = data.unread_count;
            
            // Remove both classes first, then add the appropriate one
            notificationBadge.classList.remove('hide');
            if (data.unread_count === 0) {
                notificationBadge.classList.add('hide');
            }
            
            console.log('Updated notification badge:', data.unread_count); // Debug log
        }

        // 2. Check for a security permission request and show the overlay if needed
        const overlay = document.getElementById('permission-request-overlay');
        if (overlay && data.permission_request && data.permission_request.encoding) {
            // Only show the overlay if it's not already visible
            if (!overlay.classList.contains('visible')) {
                const faceImg = document.getElementById('unknown-face-img');
                // Use a timestamp to force the browser to reload the image
                faceImg.src = `/temp_face.jpg?t=${new Date().getTime()}`;
                // Store the encoding on the overlay element itself for the local script to access
                overlay.dataset.encoding = JSON.stringify(data.permission_request.encoding);
                overlay.classList.add('visible');
            }
        }
    }

    // --- UI Interaction Logic (Theme Toggle, Sidebar) ---
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            body.classList.toggle('light-mode');
            localStorage.setItem('theme', body.classList.contains('light-mode') ? 'light' : 'dark');
        });
    }

    const isDesktop = () => window.innerWidth > 992;

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            if (!isDesktop()) return;
            body.classList.toggle('sidebar-collapsed');
            localStorage.setItem('sidebar', body.classList.contains('sidebar-collapsed') ? 'collapsed' : 'expanded');
        });
    }

    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', () => {
            body.classList.add('sidebar-open');
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', () => {
            body.classList.remove('sidebar-open');
        });
    }

    window.addEventListener('resize', () => {
        if (isDesktop()) {
            if (body.classList.contains('sidebar-open')) {
                body.classList.remove('sidebar-open');
            }
        } else {
            if (body.classList.contains('sidebar-collapsed')) {
                body.classList.remove('sidebar-collapsed');
            }
        }
    });

    // --- Start the Polling Engine ---
    fetchUpdates(); // Fetch data immediately when the page loads
    setInterval(fetchUpdates, 5000); // Then, fetch new data every 5 seconds
});
