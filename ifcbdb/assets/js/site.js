$(function(){
    $("#dataset-switcher").change(function(){
        location.href = "/" + $(this).val();
    });
})