/**
 * Created by axll on 10/24/2014.
 */

$(document).ready(function() {
    sessionid = sessionStorage.getItem('session_id');
    company_id = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    console.log('before re-authentication: ' + sessionid);

    var anOpen = [];
    var oTable = $('#contents').dataTable({
        "aaData": invoice_data,
        "aoColumns": [
            {
                "mDataProp": null,
                "sClass": "control center",
                "sDefaultContent": '<img id="expand" src="/vmi/static/src/img/details_open.png"><img id="save" src="/vmi/static/src/img/save.png">'
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
                            '<input name="company_id" value="' + company_id + '" type="hidden">' +
                            '<input name="session_id" value="' + sessionid + '" type="hidden">' +
                            '<input name="invoice_id" value="' + full["id"] + '" type="hidden">' +
                            //'<input id="comment" name="comment" type="hidden">' +
                            //'<input type="image" name="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png" alt="Submit">' +
                            //'<input type="image" name="denied" title="Deny" src="/vmi/static/src/img/gtk-no.png" alt="Submit" style="margin-left: 30px">'
                            '<button type="submit" id="approved" name="result" value="approved" title="Approve"><img title="Approve" src="/vmi/static/src/img/gtk-yes.png"></button>' +
                            '<button type="submit" id="denied" name="result" value="denied" title="Deny"><img title="Deny" src="/vmi/static/src/img/gtk-no.png"></button>' +
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
    $('#contents').on('click', '#expand', function () {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
        if (i === -1) {
            $(this).attr('src', "/vmi/static/src/img/details_close.png");
            var aData = oTable.fnGetData(nTr);
            var line_ids = aData.invoice_line;
            var uid = sessionStorage.getItem(('user_id'));
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
            $(this).attr('src', "/vmi/static/src/img/details_open.png");
            $('div.innerDetails', $(nTr).next()[0]).slideUp(function () {
                oTable.fnClose(nTr);
                anOpen.splice(i, 1);
            });
        }
    });

    $('#contents tbody').on('click', '#save', function() {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
        var aData = oTable.fnGetData(nTr);
        var line_ids = aData.invoice_line;
        var uid = sessionStorage.getItem(('user_id'));
        var rowDetails
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
                    rowDetails = data.result;
                    var title = aData.name + "-" + aData.date_invoice;
                    json2csv(rowDetails, title);
                }
            }
        });

    });

    $('#contents tbody').on('click', '#denied', function () {
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
    $('#contents tbody').on('click', '#approved', function () {
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

    function json2csv(objArray, title) {
        var array = typeof objArray != 'object' ? JSON.parse(objArray) : objArray;
        var res = '';
        var line = '';
        var fields = {"date_received": "Invoice Date", "picking_number": "Packing Number", "septa_part_number": "Septa P/N", "vendor_part_number": "Vendor P/N", "unit_of_measure": "Unit of Measure", "quantity": "Quantity", "price_unit": "Price Unit", "price_subtotal": "Price Subtotal"}
        /*for (var index in array[0]) {
            if ($.inArray(index, Object.keys(fields)) > -1){
                var value = fields[index] + "";
                line += '"' + value.replace(/"/g, '""') + '",';
            }
            //var value = index + "";
            //line += '"' + value.replace(/"/g, '""') + '",';
        }*/
        for (var index in fields){
            var value = fields[index] + "";
            line += '"' + value.replace(/"/g, '""') + '",';
        }
        line = line.slice(0, -1);
        res += line + '\r\n';
        /*for (var i = 0; i < array.length; i++) {
            var line = '';
            for (var index in array[i]) {
                if ($.inArray(index, Object.keys(fields)) > -1){
                    if (array[i][index].constructor == Array){
                        var value = array[i][index][1] + "";
                    }
                    else{
                        var value = array[i][index] + "";
                    }
                    line += '"' + value.replace(/"/g, '""') + '",';
                }
            }
            line = line.slice(0, -1);
            res += line + '\r\n';
        }*/
        for (var i = 0; i < array.length; i++) {
            var line = '';
            for (var index in fields) {
                    if (array[i][index].constructor == Array){
                        var value = array[i][index][1] + "";
                    }
                    else{
                        var value = array[i][index] + "";
                    }
                    line += '"' + value.replace(/"/g, '""') + '",';
            }
            line = line.slice(0, -1);
            res += line + '\r\n';
        }
        //window.open("data:text/csv;charset=utf-8," + escape(res));
        //var encodedUri = encodeURI(res);
        //window.open(encodedUri);
        var uri = 'data:text/csv;charset=utf-8,' + encodeURI(res);
        var downloadLink = document.createElement("a");
        downloadLink.href = uri;
        downloadLink.download = title+'.csv';
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }
});

