function getFormData(e) {
	// Serialize form fields into an object
	var formData = new FormData(document.getElementById('theform'));
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

	// Convert object to JSON and encode in base64
	return btoa(JSON.stringify(formObject));
}

function updateFormDataDisplay(e) {
	var formData = getFormData(e);
	document.getElementById('formDataDisplay').value =
		document.URL.replace("/configure", `/${formData}/manifest.json`);
}

document.addEventListener('DOMContentLoaded', function () {
	var form = document.getElementById('theform');
	form.addEventListener('input', updateFormDataDisplay);
	form.addEventListener('change', updateFormDataDisplay);
	form.addEventListener('click', updateFormDataDisplay);

	document.getElementById('theform').onsubmit = function(e) {
		e.preventDefault(); // Prevent the default form submission

		var formData = getFormData(e);
		var launchUrl = document.URL
			.replace(window.location.protocol, 'stremio:')
			.replace("/configure", `/${formData}/manifest.json`);

		console.log(launchUrl);
		// Redirect to app URL
		window.location.href = launchUrl
	};
});

document.addEventListener('DOMContentLoaded', function () {
	var providerDropdown = document.getElementById('debrid_service');
	var apiKeyInput = document.getElementById('debrid_api_key');

	providerDropdown.addEventListener('change', function() {
		apiKeyInput.value = '';
	});
});
