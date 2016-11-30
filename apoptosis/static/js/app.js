$(document).ready(function() {

	$("input#email").on("keyup", validate_register_email);
	$("input#password").on("keyup", validate_register_password);
	$("input#password_confirm").on("keyup", validate_register_password_confirm);

    handle_flash_messages();

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

function handle_flash_messages() {
    if(flash_messages.length) {
        var message_container = $("div#flash_messages");
        for(var i = 0; i < flash_messages.length; i++) {
            var message = flash_messages[i];

            var model = $("<div></div>");
            model.appendTo(message_container);
            model.attr("class", "alert alert-" + message.state + " alert-dismissible");
            model.attr("role", "alert");

            var button = $("<button></button>");
            button.appendTo(model);
            button.attr("class", "close");
            button.attr("data-dismiss", "alert");
            button.attr("aria-label", "Close");

            var cross = $("<span></span>");
            cross.appendTo(button);
            cross.attr("aria-hidden", "true");
            cross.html("&times;");

            model.append(message.message);
        }
    }
}
