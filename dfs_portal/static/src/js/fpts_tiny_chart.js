// Chart for plotting fpts in datatable
// Using amcharts.js

var {{ tableObj.v_chartData }} = [];

function {{ tableObj.fn_tableDrawCallback }}() {
    for (dataObj of {{  tableObj.v_chartData }}) {
        AmCharts.makeChart("c" + dataObj.id,
                {
                    "type": "serial",
                    "categoryField": "date",
                    "theme": "default",
                    "chartCursor": {
                        "enabled": true,
                        "animationDuration": 0,
                    },
                    "categoryAxis": {
						"equalSpacing": true,
						"parseDates": true
					},
                    "trendLines": [],
                    "graphs": [
                    {
                        "bullet": "round",
                        "lineColor": "#0B9077",
                        "id": "AmGraph-1",
                        "tabIndex": -12,
                        "title": "graph 1",
                        "valueField": "column_1",
                    }
                    ],
                    "guides": [],
                    "valueAxes": [
                    {
                        "id": "ValueAxis-1",
                        "title": ""
                    }
                    ],
                    "allLabels": [],
                    "balloon": {},
                    "titles": [],
                    "dataProvider": dataObj.points,
                }
        );
    }
    $('a[title~=JavaScript]').css('display','none');
}

$("#{{ tableObj.tableId }}").on('xhr.dt', function(e, settings, json, xhr){
    for (data of json.data) {
        var allDataObj = new Object();
        allDataObj.id  = data[0];
        var xs  = data[6].split(',');
        var y1s = data[5].split(',');
        var points = [];
        for (tup of _.zip(xs, y1s)) {
            var pointObj = new Object();
            pointObj.date = new Date(tup[0]);
            pointObj.column_1 = tup[1];
            points.push(pointObj);
        }
        points = _.sortBy(points, 'date');

        allDataObj.points = points;
        pchartsData.push(allDataObj);
        data[5] = '<div style="width: 100%; height: 100px;" id="{{ tableObj.chartIdPrefix }}' + data[0] + '"></div>'

    }

});
/*
   $("#batters-table").on('xhr.dt', function(e, settings, json, xhr){
// Insert chart data into global struct
for (data of json.data) {
var tmp = new Object();
tmp.id = data[0];
tmp.xs = data[6].split(',');
tmp.ys = data[5].split(',');
bchartsData.push(tmp);
data[5] = '<canvas id="' + data[0] + '"></canvas>'
}
});
*/

