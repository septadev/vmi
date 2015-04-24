/**
 * Created by M. A. Ruberto on 2/28/14.
 */

/* Formating function for row details */

//var sessionid = null;

$(document).ready(function(){
    sessionid = sessionStorage.getItem('session_id');
    company_id = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    var anOpen = [];
    var today = new Date();
    var yyyy = today.getFullYear();
    var mm = today.getMonth()+1;
    var fiveYearBefore = yyyy-5;
    // Initialize table
    var oTable = $('#contents').dataTable({
        "aaData": latest_history,
        "aoColumns": [
            {
                "mDataProp": null,
                "sClass": "control center",
                "sDefaultContent": '<img src="/vmi/static/src/img/details_open.png">'
            },
            {"mData": "date_done"},
            {"mData": "origin"},
            {"mData": "location_dest_id"},
            {"mData": "state"},
            {"mData": function (source, type, val) {
                var audit_state = source.contains_audit;
                var result;
                switch (audit_state) {
                    case "no":
                        result = "No Audit";
                        break;
                    case "yes":
                        result = "Auditing";
                        break;
                    case "pass":
                        result = "Pass Audit";
                        break;
                    case "fail":
                        result = "Fail Audit";
                        break;
                }
                return result;
            }
            },
            {"mData": function (source, type, val) {
                var invoice_state = source.invoice_state;
                var result;
                switch (invoice_state) {
                    case "invoiced":
                        result = "Invoiced";
                        break;
                    case "2binvoiced":
                        result = "To Be Invoiced";
                        break;
                }
                return result;
            }
            }
        ],
        "sPaginationType": "full_numbers"
    });

    //Add options to picking slip filter
    $('#year').each(function(){
        for (var i=fiveYearBefore;i<=yyyy;i++){
            $('#year').append($("<option></option>").text(i))
                .attr("value", i);
        }
        $(this).val(yyyy);
    });
    $('#month').each(function(){
        for (var i=1;i<=12;i++){
            $('#month').append($("<option></option>").text(i))
                .attr("value", i);
        }
        $(this).val(mm);
    });
    $('#day').each(function(){
        for (var i=1;i<=31;i++){
            $('#day').append($("<option></option>").text(i))
                .attr("value", i);
        }
        $(this).val(null);
    });
    $('#location').each(function(){
        var locations = stocks;
        for (var i=0;i<locations.length;i++){
            $('#location').append($("<option></option>").text(locations.records[i].name).attr("value", locations.records[i].id))
        }
    });

    //functions when submit the filter. An ajax call to pass parameters to the server. Year and month are mandatory.
    $('#filter').click(function(){
        if ($('#picking_no').val() != ""){
            console.log("search picking no");
            $.ajax({
                type: "POST",
                url: "/vmi/get_picking_no",
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '",' +
                    '"context": {"picking_no": "' + $('#picking_no').val() + '"}, ' +
                    '"company_id": "' + company_id + '"' +
                    '},"id":"VMI"}',
                error: function (XMLHttpRequest, textStatus, errorThrown) {

                },
                success: function (data) {
                    if (data.result && data.result.error) { // script returned error

                    }
                    else if (data.error) { // OpenERP error

                    } // if
                    else { // successful transaction
                        console.log('Success');
                        //destroy old table and generate a new one with respond data
                        oTable.fnClearTable(0);
                        oTable.fnAddData(data.result['records']);
                        oTable.fnDraw();
                    }
                }
            })
        }
        else if ($('#year').val() == 0 || $('#month').val() == 0){
            alert('please select specify both year and month')
        }
        else {
            var context = '{' +
                '"year": "' + $('#year').val() + '",' +
                '"month": "' + $('#month').val() + '",' +
                '"day": "' + $('#day').val() + '",' +
                '"location": "' + $('#location').val() + '",' +
                '"audit": "' + $('#audit').val() + '",' +
                '"invoice": "' + $('#invoice').val() + '"' +
                '}';
            $.ajax({
                type: "POST",
                url: "/vmi/get_upload_history",
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '",' +
                    '"context": {"year": "' + $('#year').val() + '",' +
                    '"month": "' + $('#month').val() + '",' +
                    '"day": "' + $('#day').val() + '",' +
                    '"location": "' + $('#location').val() + '",' +
                    '"audit": "' + $('#audit').val() + '",' +
                    '"invoice": "' + $('#invoice').val() + '"}, ' +
                    '"company_id": "' + company_id + '"' +
                    '},"id":"VMI"}',
                error: function (XMLHttpRequest, textStatus, errorThrown) {

                },
                success: function (data) {
                    if (data.result && data.result.error) { // script returned error

                    }
                    else if (data.error) { // OpenERP error

                    } // if
                    else { // successful transaction
                        console.log('Success');
                        //destroy old table and generate a new one with respond data
                        oTable.fnClearTable(0);
                        oTable.fnAddData(data.result['records']);
                        oTable.fnDraw();
                    }
                }
            })
        }
    });

    //Function when detail button clicked.
    $('#contents td.control').live('click', function () {
        var nTr = this.parentNode;
        var i = $.inArray(nTr, anOpen);

        if (i === -1) {
            $('img', this).attr('src', "/vmi/static/src/img/details_close.png");
            var aData = oTable.fnGetData(nTr);
            var line_ids = aData.move_lines;
            var uid = sessionStorage.getItem(('user_id'));
            var rowDetails;
            $.ajax({
                type: "POST",
                url: "/vmi/get_move_lines",
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '", "context": {}, "ids": "' + line_ids + '"},"id":"VMI"}',
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
    /*
    var anOpen = [];
    var oTable = $('#contents').dataTable({
        "aaData": history_data,
        "sDom": 'T<"clear">lfrtip',
        "oTableTools": {
            "sSwfPath": "/vmi/static/src/js/datatables/extras/TableTools/media/swf/copy_csv_xls_pdf.swf"
        },
        "aoColumns": [
            {
                "mDataProp": null,
                "sClass": "control center",
                "sDefaultContent": '<img src="/vmi/static/src/img/details_open.png">'
            },
            {"mData": "date"},
            {"mData": "origin"},
            {"mData": "state"},
            {"mData": function (source, type, val) {
                var invoice_state = source.invoice_state;
                var result;
                switch (invoice_state) {
                    case "invoiced":
                        result = "Invoiced";
                        break;
                    case "2binvoiced":
                        result = "To Be Invoiced";
                        break;
                }
                return result
            }
            }
        ],
        "sPaginationType": "full_numbers"
    });*/
  /*$('#contents td.control').live( 'click', function () {
      var nTr = this.parentNode;
      var i = $.inArray(nTr, anOpen);

      if (i === -1) {
          $('img', this).attr('src', "/vmi/static/src/img/details_close.png");
          var nDetailsRow = oTable.fnOpen(nTr, fnFormatDetails(oTable, nTr), 'details');
          $('div.innerDetails', nDetailsRow).slideDown();
          anOpen.push(nTr);
      }
      else {
          $('img', this).attr('src', "/vmi/static/src/img/details_open.png");
          $('div.innerDetails', $(nTr).next()[0]).slideUp(function () {
              oTable.fnClose(nTr);
              anOpen.splice(i, 1);
          });
      }
  });*/


    function generate_detail_table(rowDetails) {
        var classRow = 'detailRow';
        var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
        sOut += '<tr class="detailHead"><td>SEPTA P/N</td>';
        sOut += '<td>Quantity</td>';
        sOut += '<td>U of M</td>';
        sOut += '<td>Discrepency</td>';
        sOut += '<td>Category</td>';
        sOut += '<td>Vendor P/N</td>';
        sOut += '<td>Description</td></tr>\n';
        for (var i in rowDetails) {
            console.log(i);
            if (rowDetails[i].audit_fail == true) {
                classRow = 'badAudit'
            } else {
                classRow = 'detailRow'
            }
            if (i % 2 == 0) {
                classRow = 'detailRowOdd'
            }
            sOut += '<tr class="' + classRow + '"><td>' + rowDetails[i].septa_part_number + '</td>';
            sOut += '<td>' + rowDetails[i].product_qty + '</td>';
            sOut += '<td>' + rowDetails[i].product_uom[1] + '</td>';
            sOut += '<td>' + rowDetails[i].audit_fail + '</td>';
            sOut += '<td>' + rowDetails[i].categ_id[1] + '</td>';
            sOut += '<td>' + rowDetails[i].vendor_part_number + '</td>';
            sOut += '<td>' + rowDetails[i].description + '</td></tr>\n';
        }
        sOut += '</table></div>';

        return sOut;
    }

function fnFormatDetails (oTable, nTr )
{

    var aData = oTable.fnGetData( nTr );
    var classRow = 'detailRow';
    var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
    sOut += '<tr class="detailHead"><td>SEPTA P/N</td>';
    sOut += '<td>Quantity</td>';
    sOut += '<td>U of M</td>';
    sOut += '<td>Discrepency</td>';
    sOut += '<td>Category</td>';
    sOut += '<td>Location</td>';
    sOut += '<td>Vendor P/N</td>';
    sOut += '<td>Description</td></tr>\n';
    for(var i in aData.line_items){
        console.log(i);
        if(aData.line_items[i].audit_fail == true){
            classRow = 'badAudit'
        }else{
            classRow = 'detailRow'
        }
        if(i % 2 == 0){
            classRow = 'detailRowOdd'
        }
        sOut += '<tr class="'+classRow+'"><td>'+aData.line_items[i].product_details[0].default_code+'</td>';
        sOut += '<td>'+aData.line_items[i].product_qty+'</td>';
        sOut += '<td>'+aData.line_items[i].product_uom[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].audit_fail+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].categ_id[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].location_dest_id[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].vendor_part_number+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].description+'</td></tr>\n';
    }
    sOut += '</table></div>';

    return sOut;
}

});

