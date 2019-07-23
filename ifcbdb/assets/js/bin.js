//************* Local Variables ***********************/
var _bin = ""           // Bin Id
var _dataset = ""       // Dataset Name


//************* Common Methods ***********************/

// Generates a relative link to the current bin/dataset
// TODO: Verify these URLs match the current Django routes
function createLink() {
    if (_dataset != "")
        return  "/dataset/" +_dataset + "?bin_id=" + _bin;

    return "/bin/" + _bin + ".html";
}


//************* Initialization methods and page hooks ***********************/
$(function(){

    // Open the share dialog window
    $("#share-button").click(function (e) {
        e.preventDefault();

        var link = $("#share-link");
        var base = link.data("scheme") + "://" + link.data("host");

        $("#share-modal").modal();
        $("#share-link").val(base + createLink()).select();
    });

    // Copy the share link to the clipboard
    $("#copy-share-link").click(function(e) {
        e.preventDefault();

        $("#share-link").select();
        document.execCommand("Copy");
    });

});
