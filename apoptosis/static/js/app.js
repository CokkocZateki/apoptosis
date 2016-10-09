$(document).ready(function() {

	$("input#email").on("keyup", validate_register_email);
	$("input#password").on("keyup", validate_register_password);
	$("input#password_confirm").on("keyup", validate_register_password_confirm);

});

function validate_register_email() {
	return true;
}

function validate_register_password() {
	return true;
}

function validate_register_password_confirm() {
	return true;
}
