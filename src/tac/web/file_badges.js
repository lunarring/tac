// File badges script to add line count badges to modified files
(function() {
  // Keep track of files we've already processed to avoid duplicate requests
  const processedFiles = new Set();
  
  // Main function to initialize file badges
  function initFileBadges() {
    console.log("[FileBadges] Initializing...");
    
    // 1. Set up a MutationObserver to detect when new files are added
    setupFileObserver();
    
    // 2. Process any existing files
    setTimeout(findAndProcessFiles, 500);
    
    // 3. Set up file status response handler
    setupFileStatusHandler();
  }
  
  // Set up an observer to watch for changes to the file list
  function setupFileObserver() {
    const targetNode = document.getElementById('protoblockContainer');
    if (!targetNode) {
      console.log("[FileBadges] Protoblock container not found, will retry later");
      setTimeout(setupFileObserver, 1000);
      return;
    }
    
    const observer = new MutationObserver(function(mutations) {
      for (const mutation of mutations) {
        if (mutation.type === 'childList' || mutation.type === 'subtree') {
          // If files list changed, process files
          findAndProcessFiles();
        }
      }
    });
    
    observer.observe(targetNode, { 
      childList: true, 
      subtree: true
    });
    
    console.log("[FileBadges] Observer setup complete");
  }
  
  // Find and process files in the "Files to Modify" section
  function findAndProcessFiles() {
    const writeFilesList = document.getElementById('writeFilesList');
    if (!writeFilesList) {
      console.log("[FileBadges] Files list not found");
      return;
    }
    
    const fileItems = writeFilesList.querySelectorAll('li');
    console.log(`[FileBadges] Found ${fileItems.length} file items`);
    
    fileItems.forEach((item, index) => {
      const filename = getFilenameFromItem(item);
      if (!filename) return;
      
      // Skip if we've already processed this file
      if (processedFiles.has(filename)) {
        console.log(`[FileBadges] Already processed ${filename}`);
        return;
      }
      
      // Add to processed set
      processedFiles.add(filename);
      
      // Add clickable-file class
      item.classList.add('clickable-file');
      
      // Create placeholder badge
      createOrUpdateBadge(item, 0, 0);
      
      // Request file status with a delay to avoid flooding
      setTimeout(() => {
        requestFileStatus(filename);
      }, 200 * (index + 1));
    });
  }
  
  // Extract filename from list item
  function getFilenameFromItem(item) {
    // Try to get filename from text node
    for (let i = 0; i < item.childNodes.length; i++) {
      if (item.childNodes[i].nodeType === Node.TEXT_NODE) {
        const text = item.childNodes[i].nodeValue.trim();
        if (text) return text;
      }
    }
    
    // Fallback: get from textContent, removing any icon text
    return item.textContent.replace('🔍', '').trim();
  }
  
  // Create or update badge on a file item
  function createOrUpdateBadge(item, addedLines, removedLines) {
    // Check if badge already exists
    let badge = item.querySelector('.line-count-badge');
    
    // Create badge if it doesn't exist
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'line-count-badge';
      item.appendChild(badge);
    }
    
    // Clear existing content
    badge.innerHTML = '';
    
    // Add the badges
    if (addedLines > 0) {
      const addedSpan = document.createElement('span');
      addedSpan.className = 'line-count-added';
      addedSpan.textContent = `+${addedLines}`;
      badge.appendChild(addedSpan);
    }
    
    if (removedLines > 0) {
      const removedSpan = document.createElement('span');
      removedSpan.className = 'line-count-removed';
      removedSpan.textContent = `-${removedLines}`;
      badge.appendChild(removedSpan);
    }
    
    // If neither, show unknown
    if (addedLines === 0 && removedLines === 0) {
      badge.textContent = '...';
    }
  }
  
  // Request file status from server
  function requestFileStatus(filename) {
    console.log(`[FileBadges] Requesting status for ${filename}`);
    const socket = window.socket; // Use the existing socket
    
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.log("[FileBadges] Socket not available");
      return;
    }
    
    const payload = {
      type: "file_status_request",
      filename: filename
    };
    
    socket.send(JSON.stringify(payload));
  }
  
  // Set up handler for file status responses
  function setupFileStatusHandler() {
    // We need to intercept the WebSocket messages
    // Store original onmessage handler
    const originalOnMessage = window.socket.onmessage;
    
    // Replace with our own handler
    window.socket.onmessage = function(event) {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        // Not JSON, let original handler deal with it
        return originalOnMessage(event);
      }
      
      // Check if it's a file status response
      if (data.type === "file_status_response") {
        handleFileStatusResponse(data);
      }
      
      // Always call the original handler
      return originalOnMessage(event);
    };
    
    console.log("[FileBadges] File status handler setup complete");
  }
  
  // Handle file status response
  function handleFileStatusResponse(data) {
    console.log(`[FileBadges] Received status for ${data.filename}:`, data);
    
    if (!data.filename) return;
    
    const writeFilesList = document.getElementById('writeFilesList');
    if (!writeFilesList) return;
    
    const fileItems = writeFilesList.querySelectorAll('li');
    fileItems.forEach(item => {
      const itemFilename = getFilenameFromItem(item);
      
      if (itemFilename === data.filename) {
        console.log(`[FileBadges] Updating badge for ${data.filename}`);
        createOrUpdateBadge(
          item, 
          data.is_modified ? (data.added_lines || 0) : 0, 
          data.is_modified ? (data.removed_lines || 0) : 0
        );
      }
    });
  }
  
  // Start initializing after the page has loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFileBadges);
  } else {
    initFileBadges();
  }
})(); 