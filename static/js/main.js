document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video');
    const canvas = document.getElementById('overlay');
    const ctx = canvas.getContext('2d');
    const workArea = document.getElementById('workArea');
    
    let interactionCount = 0;
    let isMonitoring = false;
    let chart = null;

    // Initialize Chart
    function initChart() {
        const cCtx = document.getElementById('analyticsChart').getContext('2d');
        chart = new Chart(cCtx, {
            type: 'line',
            data: {
                labels: Array(20).fill(''),
                datasets: [{
                    label: 'Efficiency Index',
                    data: Array(20).fill(0),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    // Interaction Tracking
    workArea.addEventListener('input', () => {
        interactionCount++;
    });

    // Session Management
    window.startSession = async () => {
        const enrollment = document.getElementById('enrollInput').value;
        const res = await fetch('/api/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enrollment })
        });
        const data = await res.json();
        
        if (data.success) {
            document.getElementById('loginOverlay').classList.add('hidden');
            document.getElementById('userInfo').classList.remove('hidden');
            document.getElementById('sessionUser').innerText = data.user_name;
            startMonitoring();
        } else {
            alert(data.message);
        }
    };

    async function startMonitoring() {
        isMonitoring = true;
        initChart();
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            video.onloadedmetadata = () => {
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                heartbeat();
            };
        } catch (err) {
            console.error('Camera error:', err);
            document.getElementById('aiStatus').innerHTML = '<span class="text-red-500">Camera Access Denied</span>';
            alert('Camera Error: Please ensure you have granted camera permissions and are using localhost or 127.0.0.1.');
        }
    }

    async function heartbeat() {
        if (!isMonitoring) return;

        const offscreen = document.createElement('canvas');
        offscreen.width = video.videoWidth;
        offscreen.height = video.videoHeight;
        offscreen.getContext('2d').drawImage(video, 0, 0);
        
        // Calculate interaction rate (0 to 1)
        const rate = Math.min(interactionCount / 10, 1);
        interactionCount = 0; // Reset for next interval

        const res = await fetch('/api/monitor/heartbeat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: offscreen.toDataURL('image/jpeg', 0.5),
                interaction_rate: rate
            })
        });

        if (res.ok) {
            const data = await res.json();
            updateUI(data);
        }

        setTimeout(heartbeat, 3000);
    }

    function updateUI(data) {
        const result = data.results && data.results[0]; // Assuming single student monitoring for this view
        if (!result) return;

        // Update Focus & Engagement
        const focusVal = Math.round(result.focus * 100);
        document.getElementById('focusVal').innerText = focusVal + '%';
        document.getElementById('efficiencyBar').style.width = focusVal + '%';
        
        // Update Chart
        chart.data.datasets[0].data.shift();
        chart.data.datasets[0].data.push(focusVal);
        chart.update('none');

        // Draw Bounding Box & Metadata
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (result.bbox) {
            const isSecure = result.status === 'Verified' && result.liveness && result.spoof_check === 'Pass';
            ctx.strokeStyle = isSecure ? '#10b981' : '#f59e0b';
            if (result.spoof_check === 'Fail') ctx.strokeStyle = '#ef4444';
            
            ctx.lineWidth = 4;
            ctx.strokeRect(result.bbox[0], result.bbox[1], result.bbox[2], result.bbox[3]);
            
            ctx.fillStyle = ctx.strokeStyle;
            ctx.font = 'bold 16px Outfit';
            ctx.fillText(`${result.name} (${result.confidence}%)`, result.bbox[0], result.bbox[1] - 10);
            
            // Draw Gaze & Liveness Indicators
            ctx.font = '12px Outfit';
            ctx.fillText(`Gaze: ${result.gaze} | Liveness: ${result.liveness ? 'LIVE' : 'WAIT'}`, result.bbox[0], result.bbox[1] + result.bbox[3] + 20);
        }

        // Update AI Status Badge
        const statusBadge = document.getElementById('aiStatus');
        if (statusBadge) {
            statusBadge.innerHTML = result.spoof_check === 'Pass' 
                ? '<span class="px-2 py-1 bg-green-500/20 text-green-400 rounded-lg text-xs">IDENTIFIED & SECURE</span>'
                : '<span class="px-2 py-1 bg-red-500/20 text-red-400 rounded-lg text-xs">SPOOF ALERT</span>';
        }
    }
});
