/**
 * Created by axll on 10/24/2014.
 */

$(document).ready(function() {
    sessionid = sessionStorage.getItem('session_id');
    pid = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    console.log('before re-authentication: ' + sessionid);

    var anOpen = [];
    var oTable = $('#contents').dataTable({
        "aaData": invoice_data,
        "aoColumns": [
            {
                "mDataProp": null,
                "sClass": "control center",
                "sDefaultContent": '<img src="/vmi/static/src/img/details_open.png">'
            },
            {"mData": "date_invoice"},
            {"mData": "name"},
            {"mData": "amount_untaxed"},
            {"mData": "amount_tax"},
            {"mData": "amount_total"},
            {"mData": function (source, type, val) {
                var state = source.state;
                var result;
                switch (state) {
                    case "manager_approved":
                        result = "Septa Manager Approved";
                        break;
                    case "vendor_approved":
                        result = "Vendor Approved";
                        break;
                    case "ready":
                        result = "Ready to Pay";
                        break;
                    case "cancel":
                        result = "Cancelled";
                        break;
                }
                return result
            }
            },
            {
                "mData": null,
                "mRender": function (data, type, full) {
                    var html = '';
                    if (full["state"] == "manager_approved") {
                        var html =
                            '<form class="respond" id="respond" action="/vmi/invoice_processing" method="post" enctype="multipart/form-data">' +
                            '<input name="callback" value="debug" type="hidden">' +
                            '<input name="uid" value="' + uid + '" type="hidden">' +
                            '<input name="pid" value="' + pid + '" type="hidden">' +
                            '<input name="session_id" value="' + sessionid + '" type="hidden">' +
                            '<input name="invoice_id" value="' + full["id"] + '" type="hidden">' +
                            //'<input id="comment" name="comment" type="hidden">' +
                            //'<input type="image" name="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png" alt="Submit">' +
                            //'<input type="image" name="denied" title="Deny" src="/vmi/static/src/img/gtk-no.png" alt="Submit" style="margin-left: 30px">'
                            '<button type="submit" class="approved" name="result" value="approved" title="Approve"><img title="Approve" src="/vmi/static/src/img/gtk-yes.png"></button>' +
                            '<button type="submit" class="denied" name="result" value="denied" title="Deny"><img title="Deny" src="/vmi/static/src/img/gtk-no.png"></button>' +
                            '</form>';
                        /* +
                         '<div id="leave_comment" title="Comment" type="hidden">' +
                         '<p>Please enter the comment regarding this invoice:</p>' +
                         '<textarea rows="4" cols="50"/textarea>' +
                         '</div>';*/
                        /*function invoiceMessage(){
                         var message = prompt("Please enter the comment regarding this invoice:");
                         if (message != null){
                         $("#comment").val(message);
                         }
                         }*/
                    }
                    return html;
                }
            }
        ],
        "sPaginationType": "full_numbers"
    });
    $('#contents td.control').live('click', function () {
        var nTr = this.parentNode;
        var i = $.inArray(nTr, anOpen);

        if (i === -1) {
            $('img', this).attr('src', "/vmi/static/src/img/details_close.png");
            var aData = oTable.fnGetData(nTr);
            var line_ids = aData.invoice_line;
            var uid = sessionStorage.getItem(('user_id'));
            var rowDetails;
            $.ajax({
                type: "POST",
                url: "/vmi/get_invoice_lines",
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '", "context": {}, "ids": "' + line_ids + '", "uid": "' + uid + '"},"id":"VMI"}',
                error: function (XMLHttpRequest, textStatus, errorThrown) {

                },
                success: function (data) {
                    if (data.result && data.result.error) { // script returned error
                        $('div#loginResult').text("Warning: " + data.result.error);
                        $('div#loginResult').addClass("notice");
                    }
                    else if (data.error) { // OpenERP error
                        $('div#loginResult').text("Error-Message: " + data.error.message + " | Error-Code: " + data.error.code + " | Error-Type: " + data.error.data.type);
                        $('div#loginResult').addClass("error");
                    } // if
                    else { // successful transaction
                        var nDetailsRow = oTable.fnOpen(nTr, generate_detail_table(data.result), 'details');
                        $('div.innerDetails', nDetailsRow).slideDown();
                        anOpen.push(nTr);
                        //rowDetails = data.result;
                    }

                }
            });

        }
        else {
            $('img', this).attr('src', "/vmi/static/src/img/details_open.png");
            $('div.innerDetails', $(nTr).next()[0]).slideUp(function () {
                oTable.fnClose(nTr);
                anOpen.splice(i, 1);
            });
        }
    });

    /*$("form").submit(function(){
     var message = $("#comment").val();
     alert(message);
     message = prompt("Please enter the comment regarding this invoice:");
     if (message != null){
     $("#comment").val(message);
     }
     alert($("#comment").val());
     });*/
    /*function getComment(){
     message = $("#textarea").val();
     if (message != null){
     var app = '<input name="comment" value="' + message + '" type="hidden">';
     $("form").append(app);
     }
     }
     var dialog = "#leave_comment".dialog({
     autoOpen: false,
     height:300,
     width: 350,
     modal: true,
     buttons:{
     "Submit": getComment,
     Cancel: function(){
     dialog.dialog("close");
     }
     },
     close: function(){
     dialog.dialog("close");
     }
     });*/
    $(".denied").click(function () {
        $("form").submit(function (e) {
            //dialog.dialog("open");

            /*var myWindow = window.open("","","width=600,height=450");
             myWindow.document.write('<p>Please enter the comment regarding this invoice:</p>' +
             '<textarea rows="4" cols="50"></textarea>' +
             '<button id="submit_comment" onclick="get_comment()">Submit</button>' +
             '<button id="cancel_comment" onclick="window.close()">Cancel</button>');
             function get_comment(){
             var message = $("#textarea").val();
             window.close();
             }*/
            var message = prompt("Please enter the comment regarding this invoice:");
            if (message != null) {
                var app = '<input name="comment" value="' + message + '" type="hidden">';
                $("form").append(app);
            }
            else {
                e.preventDefault();
            }
        });
        //$(this).attr("type", "submit");
    });
    $(".approved").click(function () {
        $("form").submit(function () {
            var app = '<input name="comment" value="" type="hidden">';
            $("form").append(app);
        });
    });

    function generate_detail_table(rowDetails) {
        var classRow = 'detailRow';
        var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
        sOut += '<tr class="detailHead"><td>Deliver Date</td>';
        sOut += '<td>Packing Number</td>';
        sOut += '<td>Septa P/N</td>';
        sOut += '<td>Vendor P/N</td>';
        sOut += '<td>U of M</td>';
        sOut += '<td>Quantity</td>';
        sOut += '<td>Price Unit</td>';
        sOut += '<td>Price Subtotal</td>';
        for (var i in rowDetails) {
            console.log(i);
            if (i % 2 == 0) {
                classRow = 'detailRowOdd'
            }
            sOut += '<tr class="' + classRow + '"><td>' + rowDetails[i].date_received + '</td>';
            sOut += '<td>' + rowDetails[i].picking_number + '</td>';
            sOut += '<td>' + rowDetails[i].septa_part_number + '</td>';
            sOut += '<td>' + rowDetails[i].vendor_part_number + '</td>';
            sOut += '<td>' + rowDetails[i].unit_of_measure[1] + '</td>';
            sOut += '<td>' + rowDetails[i].quantity + '</td>';
            sOut += '<td>' + rowDetails[i].price_unit + '</td>';
            sOut += '<td>' + rowDetails[i].price_subtotal + '</td>';
        }
        sOut += '</table></div>';
        return sOut;
    }

});

