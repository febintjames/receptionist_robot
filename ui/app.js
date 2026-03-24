// ── UI State Machine ──────────────────────────────────────────────────────────
// States: splash → welcome → camera → main → welcome (loop)
let uiState = 'splash';
let pendingTransition = null;  // Buffer one transition that arrives mid-animation

const fsCamera  = document.getElementById('fullscreen-camera');
const fsWelcome = document.getElementById('welcome-screen');
const mainUI    = document.querySelector('.glass-container');

// ── DOM References ────────────────────────────────────────────────────────────
const chatLog      = document.getElementById('chat-container');
const statusText   = document.getElementById('status-text');
const statusBadge  = document.getElementById('status-indicator');
const transcriptText = document.getElementById('live-transcript');
const robotFaceUI  = document.getElementById('robot-visual');
const courseDetailUI = document.getElementById('course-detail');

// ── Transition helpers ────────────────────────────────────────────────────────

function showEl(el) {
    el.style.display = '';  // Clear any inline display override
    el.style.zIndex = '';   // Clear any inline zIndex override
    el.classList.remove('hidden', 'fade-out', 'splash-hidden', 'splash-main-hidden');
    el.classList.add('fade-in');
}

function hideEl(el, cb) {
    el.classList.remove('fade-in');
    el.classList.add('fade-out');
    setTimeout(() => {
        el.style.display = '';  // Clear inline display so .hidden class works
        el.style.zIndex = '';   // Clear inline zIndex
        el.classList.add('hidden');
        el.classList.remove('fade-out');
        if (cb) cb();
        // Replay any transition that arrived while we were animating
        if (pendingTransition) {
            const pt = pendingTransition;
            pendingTransition = null;
            pt();
        }
    }, 700);
}

// ── Splash → Welcome ──────────────────────────────────────────────────────────
(function initSplash() {
    const splash = document.getElementById('splash-screen');
    setTimeout(() => {
        splash.classList.add('splash-hidden');
        setTimeout(() => {
            splash.remove();
            if (uiState === 'splash') {
                switchScreen('welcome');
            }
        }, 800);
    }, 3500);
})();

// ── EventSource: backend events ───────────────────────────────────────────────
const eventSource = new EventSource('/events');

eventSource.onopen = () => {
    console.log('[SSE] Connected to backend');
    addSystemMessage('Connected to Neural Processor');
};

eventSource.onerror = (err) => {
    console.error('[SSE] Connection error:', err);
    addSystemMessage('Connection lost. Retrying...');
};

eventSource.addEventListener('status', (e) => {
    const { state } = JSON.parse(e.data);
    console.log('[SSE] status event received:', state, '| current uiState:', uiState);
    updateStatus(state);
    handleStateTransition(state);
});

// Dedicated event for wave → chat screen transition
// Using a separate event prevents 'Speaking' (sent during chat loop) from
// accidentally re-triggering the camera→main screen change.
eventSource.addEventListener('chat_start', () => {
    transitionCameraToMain();
});

eventSource.addEventListener('transcript', (e) => {
    const data = JSON.parse(e.data);
    transcriptText.innerText = data.text;
});

eventSource.addEventListener('message', (e) => {
    const data = JSON.parse(e.data);
    if (data.role === 'user') {
        addUserMessage(data.content);
        transcriptText.innerText = 'Thinking...';
    } else if (data.role === 'robot') {
        addRobotMessage(data.content);
        transcriptText.innerText = 'Waiting for voice input...';
    }
});

// Reset chat log when backend signals a new session
eventSource.addEventListener('reset', () => {
    clearChatLog();
    // Also exit course detail if open
    courseDetailUI.classList.add('hidden');
    robotFaceUI.classList.remove('hidden');
    const items = document.querySelectorAll('.course-item');
    items.forEach(c => c.classList.remove('selected'));
});

// ── State Transition Logic ───────────────────────────────────────────────────

// Simple, direct screen switch — no animation state machine, no race conditions
function switchScreen(target) {
    console.log('[UI] switchScreen:', uiState, '→', target);
    
    // Hide ALL screens first
    fsWelcome.classList.add('hidden');
    fsWelcome.classList.remove('fade-in', 'fade-out');
    fsCamera.classList.add('hidden');
    fsCamera.classList.remove('fade-in', 'fade-out');
    mainUI.classList.add('splash-main-hidden');
    mainUI.classList.remove('splash-main-visible');
    
    // Show the target screen
    if (target === 'welcome') {
        uiState = 'welcome';
        fsWelcome.classList.remove('hidden');
        fsWelcome.classList.add('fade-in');
    } else if (target === 'camera') {
        uiState = 'camera';
        fsCamera.classList.remove('hidden');
        fsCamera.classList.add('fade-in');
    } else if (target === 'main') {
        uiState = 'main';
        mainUI.classList.remove('splash-main-hidden');
        mainUI.classList.add('splash-main-visible');
    }
}

function transitionCameraToMain() {
    switchScreen('main');
}

function handleStateTransition(state) {
    if (state === 'PersonNearby' && uiState !== 'camera' && uiState !== 'main') {
        switchScreen('camera');
    } else if (state === 'Idle' && uiState !== 'welcome') {
        switchScreen('welcome');
        transcriptText.innerText = 'Waiting for voice input...';
    }
}

// ── Robot Face Animation ──────────────────────────────────────────────────────

function updateStatus(state) {
    statusBadge.className = 'status-badge ' + state.toLowerCase().replace(/ /g, '-');
    statusText.innerText = state;

    const robotFace = document.getElementById('robot-visual');
    if (!robotFace) return;

    if (state === 'Thinking') {
        robotFace.style.transform = 'scale(1.1)';
        robotFace.classList.remove('talking');
    } else if (state === 'Listening') {
        robotFace.style.transform = 'scale(1.05)';
        robotFace.classList.remove('talking');
    } else if (state === 'Speaking') {
        robotFace.style.transform = 'scale(1)';
        robotFace.classList.add('talking');
    } else {
        robotFace.style.transform = 'scale(1)';
        robotFace.classList.remove('talking');
    }

    // Course speaking indicator
    if (!courseDetailUI.classList.contains('hidden')) {
        const speakingIndicator = document.getElementById('course-speaking');
        if (state === 'Speaking') {
            speakingIndicator.classList.add('active');
        } else {
            speakingIndicator.classList.remove('active');
        }
    }
}

// ── Chat helpers ──────────────────────────────────────────────────────────────

function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerText = text;
    chatLog.appendChild(div);
    scrollToBottom();
}

function addRobotMessage(text) {
    const div = document.createElement('div');
    div.className = 'message robot';
    div.innerText = text;
    chatLog.appendChild(div);
    scrollToBottom();
}

function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.innerText = text;
    chatLog.appendChild(div);
    scrollToBottom();
}

function clearChatLog() {
    chatLog.innerHTML = '';
}

function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
}

// ── Course Sidebar Logic ──────────────────────────────────────────────────────

const courseItems = document.querySelectorAll('.course-item');
const backBtn = document.getElementById('course-back-btn');
const detailTitle     = document.getElementById('course-detail-title');
const detailDuration  = document.getElementById('course-detail-duration');
const detailDesc      = document.getElementById('course-detail-desc');
const detailHighlights = document.getElementById('course-detail-highlights');

courseItems.forEach(item => {
    item.addEventListener('click', async () => {
        const courseName = item.dataset.course;
        courseItems.forEach(c => c.classList.remove('selected'));
        item.classList.add('selected');
        try {
            await fetch('/api/course-select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ course: courseName })
            });
        } catch (error) {
            console.error('Error selecting course:', error);
        }
    });
});

backBtn.addEventListener('click', () => {
    courseDetailUI.classList.add('hidden');
    robotFaceUI.classList.remove('hidden');
    courseItems.forEach(c => c.classList.remove('selected'));
});

eventSource.addEventListener('course-detail', (e) => {
    const course = JSON.parse(e.data);
    detailTitle.innerHTML    = course.title;
    detailDuration.innerHTML = course.duration;
    detailDesc.innerHTML     = course.description;

    detailHighlights.innerHTML = '';
    course.highlights.forEach(h => {
        const tag = document.createElement('span');
        tag.className = 'course-highlight-tag';
        tag.innerText = h;
        detailHighlights.appendChild(tag);
    });

    robotFaceUI.classList.add('hidden');
    courseDetailUI.classList.remove('hidden');
});
