/**
 * Created by axll on 10/24/2014.
 */

$(document).ready(function() {
    sessionid = sessionStorage.getItem('session_id');
    company_id = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    //invoice_data = updateData();
    var anOpen = [];
    var oTable = $('#contents').dataTable({
        "aaData": invoice_data,
        "aoColumns": [
            // Add pic to a datatable
            {
                "mDataProp": null,
                "sClass": "control center",
                "sDefaultContent": '<img id="expand" src="/vmi/static/src/img/details_open.png"><img id="save" src="/vmi/static/src/img/save.png">'
            },
            {"mData": "date_invoice"},
            {"mData": function (source, type, val){
                var fullLocation = source.location_id[1];
                var loc = fullLocation.split(" / ");
                if (loc.length > 2){
                    return loc[2]
                }
                else{
                    return loc[0]
                }
            }},
            {"mData": function (source, type, val){
                var fullCategory = source.category_id[1];
                var loc = fullCategory.split(" / ");
                if (loc.length > 1){
                    return loc[1]
                }
                else{
                    return loc[0]
                }
            }},
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
            // Using a function, add pics to dataTable
            {
                "mData": null,
                "mRender": function (data, type, full) {
                    var html = '';
                    if (full["state"] == "manager_approved") {
                        var html =
                            '<img id="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png"></button>' +
                            '<img id="denied" title="Deny" title="Deny" src="/vmi/static/src/img/gtk-no.png" style="margin-left: 25px"></button>'
                    }
                    return html;
                }
            }
        ],
        "sPaginationType": "full_numbers"
    });

    //Function to get invoice detail
    $('#contents').on('click', '#expand', function () {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
        if (i === -1) {
            $(this).attr('src', "/vmi/static/src/img/details_close.png");
            var aData = oTable.fnGetData(nTr);
            var line_ids = aData.invoice_line;
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

    // Save the invoice detail
    $('#contents tbody').on('click', '#save', function() {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
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
                    rowDetails = data.result;
                    var title = aData.location_id + "=" + aData.category_id + "-" + aData.date_invoice;
                    json2csv(rowDetails, title);
                }
            }
        });

    });

    //approve button clicked
    $('#contents tbody').on('click', '#approved', function () {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
        var aData = oTable.fnGetData(nTr);
        var invoice_id = aData.id;
        var decision = {
            invoice_id: invoice_id,
            approved: true,
            comment: ''
        };
        process_invoice(decision, nTr);

    });

    // denied button clicked
    $('#contents tbody').on('click', '#denied', function () {
        var nTr = this.parentNode.parentNode;
        var i = $.inArray(nTr, anOpen);
        var aData = oTable.fnGetData(nTr);
        var invoice_id = aData.id;
        // prompt a message to store the reason denied
        var message = prompt("Please enter the comment regarding this invoice:");
        if (message != null) {
            var decision = {
                invoice_id: invoice_id,
                approved: false,
                comment: message
            };
            process_invoice(decision, nTr);
        }
        else {
            e.preventDefault();
        }
    });

    // Ajax to get all invoices from server
    // Not been used yet
    function updateData(){
        var result = [];
        $.ajax({
            type: "POST",
            url: "/vmi/get_invoices",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            async: false,
            data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '",' +
                    '"context": {}, ' +
                    '"company_id": "' + company_id + '"' +
                    '},"id":"VMI"}',
            error: function (XMLHttpRequest, textStatus, errorThrown) {
                console.log(XMLHttpRequest, textStatus, errorThrown);
            },
            success: function (data) {
                if (data.result && data.result.code) { // script returned error
                }
                else if (data.error) { // OpenERP error
                } // if
                else { // successful transaction
                    result = data.result
                }
            }
        });
        return result
    }

    // ajax to process the invoice, approve or deny
    function process_invoice(decision, nTr){
        //var oTable = $('#contents').dataTable();
        $.ajax({
            type: "POST",
            url: "/vmi/process_invoice",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            async: false,
            data: '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": "' + sessionid + '", "context": {}, "ids": "' + decision.invoice_id + '", "company_id": "' + company_id + '", "decision": "' + decision.approved + '", "comment": "' + decision.comment + '"}, "id":"VMI"}',
            error: function (XMLHttpRequest, textStatus, errorThrown) {
                console.log(XMLHttpRequest, textStatus, errorThrown);
            },
            success: function (data) {
                if (data.result && data.result.code) { // script returned error
                }
                else if (data.error) { // OpenERP error
                } // if
                else { // successful transaction
                    // Change displayed status and hide the processing button
                    if (decision.approved == true){
                        $(nTr).find(":nth-child(8)").html('Vendor Approved');
                    }
                    else {
                        $(nTr).find(":nth-child(8)").html('Vendor Denied');
                    }
                    $(nTr).find('#approved, #denied').hide();
                }
            }
        });
    }

    // show the invoice detail
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

    // convert json data to csv file
    function json2csv(objArray, title) {
        var array = typeof objArray != 'object' ? JSON.parse(objArray) : objArray;
        var res = '';
        var line = '';
        var fields = {"date_received": "Invoice Date", "picking_number": "Packing Number", "septa_part_number": "Septa P/N", "vendor_part_number": "Vendor P/N", "unit_of_measure": "Unit of Measure", "quantity": "Quantity", "price_unit": "Price Unit", "price_subtotal": "Price Subtotal"}
        for (var index in fields){
            var value = fields[index] + "";
            line += '"' + value.replace(/"/g, '""') + '",';
        }
        line = line.slice(0, -1);
        res += line + '\r\n';
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

        // Download the csv file
        var uri = 'data:text/csv;charset=utf-8,' + encodeURI(res);
        var downloadLink = document.createElement("a");
        downloadLink.href = uri;
        downloadLink.download = title+'.csv';
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }
});

