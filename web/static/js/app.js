/**
 * M3U2strm3 Web Interface JavaScript Application
 */

class M3U2strm3Dashboard {
    constructor() {
        this.ws = null;
        this.wsConnected = false;
        this.retryAttempts = 0;
        this.maxRetries = 5;
        this.retryDelay = 1000;
        
        // Elements
        this.elements = {
            systemStatusText: document.getElementById('system-status-text'),
            currentJobStatus: document.getElementById('current-job-status'),
            queueLength: document.getElementById('queue-length'),
            strmCount: document.getElementById('strm-count'),
            overallProgressBar: document.getElementById('overall-progress-bar'),
            currentPhase: document.getElementById('current-phase'),
            phaseProgressText: document.getElementById('phase-progress-text'),
            currentItem: document.getElementById('current-item'),
            processingSpeed: document.getElementById('processing-speed'),
            elapsedTime: document.getElementById('elapsed-time'),
            statsMovies: document.getElementById('stats-movies'),
            statsTv: document.getElementById('stats-tv'),
            statsDocs: document.getElementById('stats-docs'),
            statsAllowed: document.getElementById('stats-allowed'),
            jobsTableBody: document.getElementById('jobs-table-body'),
            errorAlert: document.getElementById('error-alert'),
            errorMessage: document.getElementById('error-message'),
            refreshJobsBtn: document.getElementById('refresh-jobs-btn'),
            startProcessingBtn: document.getElementById('start-processing-btn')
        };
        
        // Bind methods
        this.connectWebSocket = this.connectWebSocket.bind(this);
        this.handleWebSocketMessage = this.handleWebSocketMessage.bind(this);
        this.updateDashboard = this.updateDashboard.bind(this);
        this.showError = this.showError.bind(this);
        this.hideError = this.hideError.bind(this);
    }
    
    init() {
        console.log('Initializing M3U2strm3 Dashboard...');
        
        // Initialize WebSocket connection
        this.connectWebSocket();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Initial data fetch
        this.fetchInitialData();
        
        // Start periodic updates
        this.startPeriodicUpdates();
    }
    
    setupEventListeners() {
        // Refresh jobs button
        if (this.elements.refreshJobsBtn) {
            this.elements.refreshJobsBtn.addEventListener('click', () => {
                this.fetchJobs();
            });
        }
        
        // Error alert dismiss
        if (this.elements.errorAlert) {
            this.elements.errorAlert.addEventListener('closed.bs.alert', () => {
                this.hideError();
            });
        }
    }
    
    connectWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/progress`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.wsConnected = true;
                this.retryAttempts = 0;
                this.updateConnectionStatus(true);
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.wsConnected = false;
                this.updateConnectionStatus(false);
                this.handleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.wsConnected = false;
                this.updateConnectionStatus(false);
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.handleReconnect();
        }
    }
    
    handleReconnect() {
        if (this.retryAttempts < this.maxRetries) {
            this.retryAttempts++;
            const delay = this.retryDelay * Math.pow(2, this.retryAttempts - 1); // Exponential backoff
            
            console.log(`WebSocket reconnect attempt ${this.retryAttempts}/${this.maxRetries} in ${delay}ms`);
            
            setTimeout(() => {
                this.connectWebSocket();
            }, delay);
        } else {
            console.error('Max WebSocket reconnection attempts reached');
            this.showError('WebSocket connection failed. Please refresh the page.');
        }
    }
    
    updateConnectionStatus(connected) {
        const indicator = document.getElementById('status-indicator');
        const text = document.getElementById('status-text');
        
        if (connected) {
            indicator.className = 'fas fa-circle text-success me-1';
            text.textContent = 'Online';
            text.className = 'text-success';
        } else {
            indicator.className = 'fas fa-circle text-danger me-1';
            text.textContent = 'Offline';
            text.className = 'text-danger';
        }
    }
    
    handleWebSocketMessage(data) {
        this.updateDashboard(data);
    }
    
    updateDashboard(data) {
        // Update progress information
        if (data.overall_progress !== undefined) {
            this.updateProgressBar(data.overall_progress);
        }
        
        if (data.current_phase) {
            this.elements.currentPhase.value = data.current_phase;
            this.elements.phaseProgressText.textContent = `${Math.round(data.phase_progress || 0)}%`;
        }
        
        if (data.current_item) {
            this.elements.currentItem.value = data.current_item;
        }
        
        if (data.items_per_second !== undefined) {
            this.elements.processingSpeed.value = `${data.items_per_second.toFixed(1)} items/sec`;
        }
        
        if (data.elapsed_time !== undefined) {
            this.elements.elapsedTime.value = this.formatTime(data.elapsed_time);
        }
        
        // Update statistics
        if (data.stats) {
            this.updateStatistics(data.stats);
        }
        
        // Update job status
        if (data.is_complete) {
            this.elements.currentJobStatus.textContent = 'Completed';
            this.elements.currentJobStatus.className = 'badge bg-success';
        } else if (data.is_error) {
            this.elements.currentJobStatus.textContent = 'Error';
            this.elements.currentJobStatus.className = 'badge bg-danger';
        } else if (data.current_phase && data.current_phase !== 'Idle') {
            this.elements.currentJobStatus.textContent = 'Processing';
            this.elements.currentJobStatus.className = 'badge bg-primary';
        } else {
            this.elements.currentJobStatus.textContent = 'None';
            this.elements.currentJobStatus.className = 'badge bg-secondary';
        }
        
        // Update error message if present
        if (data.error_message) {
            this.showError(data.error_message);
        } else {
            this.hideError();
        }
    }
    
    updateProgressBar(progress) {
        const percentage = Math.round(progress);
        this.elements.overallProgressBar.style.width = `${percentage}%`;
        this.elements.overallProgressBar.textContent = `${percentage}%`;
        
        // Update progress bar color based on progress
        if (progress >= 100) {
            this.elements.overallProgressBar.className = 'progress-bar bg-success progress-bar-striped';
        } else if (progress > 0) {
            this.elements.overallProgressBar.className = 'progress-bar bg-primary progress-bar-striped progress-bar-animated';
        } else {
            this.elements.overallProgressBar.className = 'progress-bar bg-secondary';
        }
    }
    
    updateStatistics(stats) {
        this.elements.statsMovies.textContent = stats.movies_allowed || 0;
        this.elements.statsTv.textContent = stats.tv_episodes_allowed || 0;
        this.elements.statsDocs.textContent = stats.documentaries_allowed || 0;
        
        const totalAllowed = (stats.movies_allowed || 0) + (stats.tv_episodes_allowed || 0) + (stats.documentaries_allowed || 0);
        this.elements.statsAllowed.textContent = totalAllowed;
        
        // Update STRM count
        this.elements.strmCount.textContent = stats.strm_created || 0;
    }
    
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    async fetchInitialData() {
        try {
            // Fetch system status
            const statusResponse = await fetch('/api/status');
            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                this.updateSystemStatus(statusData);
            }
            
            // Fetch jobs
            this.fetchJobs();
            
        } catch (error) {
            console.error('Error fetching initial data:', error);
            this.showError('Failed to fetch initial data');
        }
    }
    
    updateSystemStatus(statusData) {
        if (statusData.current_job) {
            this.elements.currentJobStatus.textContent = statusData.current_job.job_id;
            this.elements.currentJobStatus.className = 'badge bg-primary';
        } else {
            this.elements.currentJobStatus.textContent = 'None';
            this.elements.currentJobStatus.className = 'badge bg-secondary';
        }
        
        this.elements.queueLength.textContent = statusData.queue_length || 0;
    }
    
    async fetchJobs() {
        try {
            const response = await fetch('/api/jobs');
            if (response.ok) {
                const jobsData = await response.json();
                this.renderJobsTable(jobsData);
            }
        } catch (error) {
            console.error('Error fetching jobs:', error);
        }
    }
    
    renderJobsTable(jobs) {
        const tbody = this.elements.jobsTableBody;
        tbody.innerHTML = '';
        
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No jobs found</td></tr>';
            return;
        }
        
        jobs.forEach(job => {
            const row = document.createElement('tr');
            
            const statusClass = this.getStatusBadgeClass(job.status);
            const duration = job.duration ? this.formatTime(job.duration) : 'N/A';
            
            row.innerHTML = `
                <td><code>${job.job_id}</code></td>
                <td><span class="badge ${statusClass}">${job.status}</span></td>
                <td>
                    <div class="progress" style="height: 10px;">
                        <div class="progress-bar" style="width: ${job.progress || 0}%"></div>
                    </div>
                </td>
                <td>${job.start_time ? new Date(job.start_time).toLocaleString() : 'N/A'}</td>
                <td>${duration}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-primary" onclick="viewJobDetails('${job.job_id}')">
                            <i class="fas fa-eye"></i>
                        </button>
                        ${job.status === 'running' ? `
                            <button class="btn btn-outline-danger" onclick="stopJob('${job.job_id}')">
                                <i class="fas fa-stop"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    }
    
    getStatusBadgeClass(status) {
        switch (status) {
            case 'pending': return 'badge-pending';
            case 'running': return 'badge-running';
            case 'completed': return 'badge-completed';
            case 'failed': return 'badge-failed';
            case 'stopped': return 'badge-stopped';
            default: return 'badge-secondary';
        }
    }
    
    startPeriodicUpdates() {
        // Update every 5 seconds
        setInterval(() => {
            this.fetchJobs();
        }, 5000);
    }
    
    showError(message) {
        if (this.elements.errorAlert && this.elements.errorMessage) {
            this.elements.errorMessage.textContent = message;
            this.elements.errorAlert.style.display = 'block';
        }
    }
    
    hideError() {
        if (this.elements.errorAlert) {
            this.elements.errorAlert.style.display = 'none';
        }
    }
}

// Global functions for button actions
async function stopCurrentJob() {
    try {
        const response = await fetch('/api/stop', {
            method: 'POST'
        });
        
        if (response.ok) {
            showToast('Job stopped successfully', 'success');
        } else {
            const error = await response.json();
            showToast(error.message || 'Failed to stop job', 'error');
        }
    } catch (error) {
        console.error('Error stopping job:', error);
        showToast('Error stopping job', 'error');
    }
}

async function viewJobDetails(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}`);
        if (response.ok) {
            const job = await response.json();
            showJobModal(job);
        }
    } catch (error) {
        console.error('Error fetching job details:', error);
        showToast('Error fetching job details', 'error');
    }
}

function showToast(message, type = 'info') {
    // Simple toast implementation
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} alert-dismissible fade show position-fixed`;
    toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(toast);
    
    // Auto-dismiss after 3 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 3000);
}

function showJobModal(job) {
    // Simple modal implementation
    const modal = document.createElement('div');
    modal.className = 'modal fade show';
    modal.style.display = 'block';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Job Details: ${job.job_id}</h5>
                    <button type="button" class="btn-close" onclick="this.closest('.modal').remove()"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-6">
                            <strong>Status:</strong> <span class="badge ${getStatusBadgeClass(job.status)}">${job.status}</span><br>
                            <strong>Progress:</strong> ${job.progress || 0}%<br>
                            <strong>Start Time:</strong> ${job.start_time ? new Date(job.start_time).toLocaleString() : 'N/A'}<br>
                            <strong>End Time:</strong> ${job.end_time ? new Date(job.end_time).toLocaleString() : 'N/A'}<br>
                            <strong>Duration:</strong> ${job.duration ? formatTime(job.duration) : 'N/A'}<br>
                        </div>
                        <div class="col-md-6">
                            ${job.error_message ? `<strong>Error:</strong> <span class="text-danger">${job.error_message}</span><br>` : ''}
                            ${job.result ? `
                                <strong>Result:</strong><br>
                                <ul>
                                    <li>Movies Found: ${job.result.stats?.movies_found || 0}</li>
                                    <li>Movies Allowed: ${job.result.stats?.movies_allowed || 0}</li>
                                    <li>TV Episodes Found: ${job.result.stats?.tv_episodes_found || 0}</li>
                                    <li>TV Episodes Allowed: ${job.result.stats?.tv_episodes_allowed || 0}</li>
                                    <li>STRM Created: ${job.result.stats?.strm_created || 0}</li>
                                </ul>
                            ` : ''}
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop fade show';
    document.body.appendChild(backdrop);
}

// Helper functions
function getStatusBadgeClass(status) {
    switch (status) {
        case 'pending': return 'badge-pending';
        case 'running': return 'badge-running';
        case 'completed': return 'badge-completed';
        case 'failed': return 'badge-failed';
        case 'stopped': return 'badge-stopped';
        default: return 'badge-secondary';
    }
}

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on the dashboard page
    if (document.getElementById('system-status-text')) {
        window.dashboard = new M3U2strm3Dashboard();
        window.dashboard.init();
    }
});
