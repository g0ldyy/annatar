setTimeout(function (){
	document.getElementById('theform').onsubmit = function(e) {
		e.preventDefault(); // Prevent the default form submission

		// Serialize form fields into an object
		var formData = new FormData(e.target);
		var formObject = {};
		formData.forEach(function(value, key){
			if (key.endsWith('[]')) {
				// Remove '[]' from the key name
				var cleanKey = key.slice(0, -2);
				// Initialize the array if it doesn't exist
				if (!formObject[cleanKey]) {
					formObject[cleanKey] = [];
				}
				// Push the value into the array
				formObject[cleanKey].push(value);
			} else {
				// Handle regular field
				formObject[key] = value;
			}
		});
		console.log(formObject);

		// Convert object to JSON and encode in base64
		var base64EncodedData = btoa(JSON.stringify(formObject));
		var launchUrl = 'stremio://' + window.location.hostname + '/' + base64EncodedData + '/manifest.json';
		console.log(launchUrl);
		// Redirect to app URL
		window.location.href = launchUrl
	};
}, 300);
