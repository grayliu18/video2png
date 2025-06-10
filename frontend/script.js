document.addEventListener('DOMContentLoaded', () => {
    // DOM element references
    const videoInput = document.getElementById('video-input');
    const fileListDiv = document.getElementById('file-list');
    const fpsInput = document.getElementById('fps-input');
    const convertButton = document.getElementById('convert-button');
    const statusArea = document.getElementById('status-area');
    const downloadArea = document.getElementById('download-area');
    const dropArea = document.getElementById('drop-area');
    const progressBarContainer = document.getElementById('progress-bar-container');
    const progressBar = document.getElementById('progress-bar');
    const errorDetailsDiv = document.getElementById('error-details');
    const errorListUl = document.getElementById('error-list');
    const customFpsCheckbox = document.getElementById('custom-fps-checkbox');
    const fpsInputContainer = document.getElementById('fps-input-container');
    const clearListButton = document.getElementById('clear-list-button'); // New button

    let currentFiles = []; // Store the File objects
    let currentTaskId = null;
    let statusInterval = null;
    const POLLING_INTERVAL = 3000; // Poll status every 3 seconds

    // --- Utility Functions ---
    function updateFileList() {
        fileListDiv.innerHTML = ''; // Clear existing list
        if (currentFiles.length === 0) {
            fileListDiv.innerHTML = '<p><i>尚未选择文件</i></p>';
            convertButton.disabled = true;
            clearListButton.style.display = 'none'; // Hide clear button when list is empty
        } else {
            currentFiles.forEach((file, index) => {
                const fileItemDiv = document.createElement('div');
                fileItemDiv.classList.add('file-item');

                const fileNameSpan = document.createElement('span');
                let fileSize = file.size;
                let sizeUnit = 'bytes';
                if (fileSize > 1024 * 1024) {
                    fileSize = (fileSize / (1024 * 1024)).toFixed(2);
                    sizeUnit = 'MB';
                } else if (fileSize > 1024) {
                    fileSize = (fileSize / 1024).toFixed(2);
                    sizeUnit = 'KB';
                }
                fileNameSpan.textContent = `${file.name} (${fileSize} ${sizeUnit})`;

                const deleteButton = document.createElement('button');
                deleteButton.classList.add('delete-file-button');
                deleteButton.textContent = '❌'; // Use text 'X' or an icon
                deleteButton.title = '移除此文件';
                deleteButton.dataset.index = index; // Store index to identify which file to remove

                fileItemDiv.appendChild(fileNameSpan);
                fileItemDiv.appendChild(deleteButton);
                fileListDiv.appendChild(fileItemDiv);
            });
            convertButton.disabled = false;
            clearListButton.style.display = 'block'; // Show clear button when list has items
        }
        // Only reset status/download, not the file list itself
        // resetStatusAndDownload(); // Don't call this here, it clears status unnecessarily
    }

    function updateStatus(message, statusClass = '', progress = null, errors = []) {
        // (Function remains the same as before)
        statusArea.innerHTML = `<p class="${statusClass}">${message}</p>`;
        if (progress !== null && progress >= 0 && progress <= 1) {
            progressBarContainer.style.display = 'block';
            const percentage = (progress * 100).toFixed(1);
            progressBar.style.width = `${percentage}%`;
            progressBar.textContent = `${percentage}%`;
        } else {
            progressBarContainer.style.display = 'none';
            progressBar.style.width = '0%';
            progressBar.textContent = '';
        }
        errorListUl.innerHTML = '';
        if (errors && errors.length > 0) {
            errors.forEach(err => {
                const li = document.createElement('li');
                li.textContent = `${err.file_name}: ${err.message}`;
                errorListUl.appendChild(li);
            });
            errorDetailsDiv.style.display = 'block';
        } else {
            errorDetailsDiv.style.display = 'none';
        }
    }

    function resetStatusAndDownload() {
        // (Function remains the same as before)
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
        currentTaskId = null;
        updateStatus('<i>等待开始...</i>');
        downloadArea.innerHTML = '<p><i>转换完成后将在此处提供下载链接。</i></p>';
        convertButton.disabled = currentFiles.length === 0; // Re-enable based on file list
        progressBarContainer.style.display = 'none';
        errorDetailsDiv.style.display = 'none';
    }

    function pollStatus() {
        // (Function remains the same as before)
        if (!currentTaskId) return;

        fetch(`/status/${currentTaskId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                let statusMessage = '';
                let statusClass = '';
                let isDone = false;
                const actualFps = data.fps ? ` (FPS: ${data.fps})` : '';

                switch (data.status) {
                    case 'uploaded':
                        statusMessage = '文件已上传，等待开始转换...';
                        statusClass = 'status-uploaded';
                        break;
                    case 'queued':
                        statusMessage = `任务已加入队列，等待处理...${actualFps}`;
                        statusClass = 'status-queued';
                        break;
                    case 'processing':
                        const processed = data.processed_files || 0;
                        const total = data.total_files || 0;
                        statusMessage = `正在处理: ${processed} / ${total} 文件...${actualFps}`;
                        statusClass = 'status-processing';
                        break;
                    case 'complete':
                        statusMessage = `转换完成！ ${data.successful_files.length} 个文件成功。${actualFps}`;
                        statusClass = 'status-complete';
                        isDone = true;
                        break;
                    case 'failed':
                         const successCount = data.successful_files.length;
                         const failCount = data.failed_files.length;
                         statusMessage = `任务完成。成功: ${successCount}, 失败: ${failCount}。${actualFps}`;
                        statusClass = 'status-failed';
                        isDone = true;
                        break;
                    default:
                        statusMessage = `未知状态: ${data.status}`;
                }

                updateStatus(statusMessage, statusClass, data.progress, data.failed_files);

                if (isDone) {
                    clearInterval(statusInterval);
                    statusInterval = null;
                    convertButton.disabled = currentFiles.length === 0; // Re-enable based on file list

                    if (data.successful_files.length > 0) {
                        downloadArea.innerHTML = `<a href="/download/${currentTaskId}" download="apng_results_${currentTaskId}.zip">下载成功结果 (ZIP)</a>`;
                    } else {
                        downloadArea.innerHTML = '<p><i>所有文件转换失败或无成功文件，无结果可下载。</i></p>';
                    }
                }
            })
            .catch(error => {
                console.error('轮询状态时出错:', error);
                updateStatus(`轮询状态时出错: ${error.message}`, 'status-failed');
                clearInterval(statusInterval);
                statusInterval = null;
                convertButton.disabled = currentFiles.length === 0; // Re-enable based on file list
            });
    }

    // --- Event Listeners ---

    // Handle file selection via input
    videoInput.addEventListener('change', (event) => {
        // Append new files instead of replacing
        currentFiles.push(...Array.from(event.target.files));
        // Reset the input value so the same file can be selected again if removed
        event.target.value = null;
        updateFileList();
        resetStatusAndDownload(); // Reset status when files change
    });

    // Handle drag and drop
    dropArea.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropArea.classList.add('highlight');
    });
    dropArea.addEventListener('dragleave', () => {
        dropArea.classList.remove('highlight');
    });
    dropArea.addEventListener('drop', (event) => {
        event.preventDefault();
        dropArea.classList.remove('highlight');
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            const acceptedTypes = videoInput.accept.split(',').map(t => t.trim());
            const newFiles = Array.from(files).filter(file => {
                 return acceptedTypes.some(type => {
                     if (type.endsWith('/*')) {
                         return file.type.startsWith(type.slice(0, -1));
                     }
                     return file.type === type;
                 });
            });
             if (newFiles.length < files.length) {
                 alert("已自动过滤掉非视频文件。");
             }
            currentFiles.push(...newFiles);
            updateFileList();
            resetStatusAndDownload(); // Reset status when files change
        }
    });

    // Trigger file input click when drop area (not label) is clicked
    dropArea.addEventListener('click', (e) => {
        if (e.target !== videoInput && e.target.tagName !== 'LABEL') {
             videoInput.click();
        }
    });

    // Handle Custom FPS Checkbox change
    customFpsCheckbox.addEventListener('change', () => {
        if (customFpsCheckbox.checked) {
            fpsInputContainer.style.display = 'flex';
            fpsInput.value = '30'; // Set default custom FPS
        } else {
            fpsInputContainer.style.display = 'none';
        }
    });

    // FPS Input Validation (only allow digits)
    fpsInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^0-9]/g, '');
    });

    // Handle clicks within the file list (for delete buttons) using event delegation
    fileListDiv.addEventListener('click', (event) => {
        if (event.target.classList.contains('delete-file-button')) {
            const indexToRemove = parseInt(event.target.dataset.index, 10);
            if (!isNaN(indexToRemove) && indexToRemove >= 0 && indexToRemove < currentFiles.length) {
                currentFiles.splice(indexToRemove, 1); // Remove file from array
                updateFileList(); // Update the displayed list
                resetStatusAndDownload(); // Reset status when files change
            }
        }
    });

    // Handle Clear List button click
    clearListButton.addEventListener('click', () => {
        currentFiles = []; // Empty the array
        videoInput.value = null; // Clear the file input visually
        updateFileList(); // Update the displayed list
        resetStatusAndDownload(); // Reset status when files change
    });


    // Handle conversion button click
    convertButton.addEventListener('click', async () => {
        if (currentFiles.length === 0) {
            alert('请先选择要转换的视频文件。');
            return;
        }

        let fpsToSend = null;
        if (customFpsCheckbox.checked) {
            // Validate FPS input more strictly here
            const fpsValueRaw = fpsInput.value.trim();
            if (!/^[1-9]\d*$/.test(fpsValueRaw)) { // Regex for positive integer
                 alert('请输入有效的正整数作为自定义 FPS。');
                 return;
            }
            const fpsValue = parseInt(fpsValueRaw, 10);
             if (isNaN(fpsValue) || fpsValue <= 0) { // Double check after parseInt
                 alert('请输入有效的正整数作为自定义 FPS。');
                 return;
             }
            fpsToSend = fpsValue;
        }

        convertButton.disabled = true;
        resetStatusAndDownload(); // Clear previous results before starting
        updateStatus('正在上传文件...', 'status-processing');

        const formData = new FormData();
        currentFiles.forEach(file => {
            formData.append('files', file);
        });

        try {
            // 1. Upload files
            const uploadResponse = await fetch('/upload', {
                method: 'POST',
                body: formData,
            });
            if (!uploadResponse.ok) {
                const errorData = await uploadResponse.json().catch(() => ({ detail: '上传失败，无法解析错误信息。' }));
                throw new Error(`上传失败: ${errorData.detail || uploadResponse.statusText}`);
            }
            const uploadResult = await uploadResponse.json();
            currentTaskId = uploadResult.task_id;
            updateStatus('上传成功，正在请求转换...', 'status-uploaded');

            // 2. Start conversion
            const convertPayload = { task_id: currentTaskId };
            if (fpsToSend !== null) {
                convertPayload.fps = fpsToSend;
            }

            const convertResponse = await fetch('/convert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(convertPayload),
            });
            if (!convertResponse.ok) {
                 const errorData = await convertResponse.json().catch(() => ({ detail: '请求转换失败，无法解析错误信息。' }));
                throw new Error(`请求转换失败: ${errorData.detail || convertResponse.statusText}`);
            }
            const convertResult = await convertResponse.json();
            updateStatus('转换任务已加入队列，正在处理...', 'status-queued');

            // 3. Start polling status
            if (statusInterval) clearInterval(statusInterval);
            statusInterval = setInterval(pollStatus, POLLING_INTERVAL);
            pollStatus(); // Poll immediately once

        } catch (error) {
            console.error('处理过程中出错:', error);
            updateStatus(`错误: ${error.message}`, 'status-failed');
            convertButton.disabled = false; // Re-enable on error
        }
    });

    // Initial setup
    updateFileList(); // Initial call to display "No files selected" and hide clear button
});
