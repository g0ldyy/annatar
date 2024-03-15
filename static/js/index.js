function getFormData(e) {
	// Serialize form fields into an object
	var formData = new FormData(document.getElementById('theform'));
	var formObject = {
		"filters": Array.from(document.querySelectorAll('input[type="checkbox"]:not(:checked)')).map(x => x.id),
	};
	formData.forEach(function(value, key){
		// Remove '[]' from the key name
		var isList = key.endsWith('[]');
		var cleanKey = isList ? key.slice(0, -2) : key;
		if (cleanKey === "filters") {
			return;
		}
		// Initialize the array if it doesn't exist
		if (isList) {
			if (!formObject[cleanKey]) {
				formObject[cleanKey] = [];
			}
			// Push the value into the array
			formObject[cleanKey].push(value);
		} else {
			formObject[key] = value;
		}
	});

	// Convert object to JSON and encode in base64
	return btoa(JSON.stringify(formObject));
}

function updateFormDataDisplay(e) {
	var formData = getFormData(e);
	document.getElementById('formDataDisplay').value = `${window.location.protocol}//${window.location.hostname}${window.location.port ? ':' + window.location.port : ''}/${formData}/manifest.json`;
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
