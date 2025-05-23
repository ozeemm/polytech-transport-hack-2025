from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import os

from geojson_func import *

app = Flask(__name__)
CORS(app)

def get_db_connection():
    conn = sqlite3.connect('Hack.db')
    conn.row_factory = sqlite3.Row
    return conn


def get_AV_speed_colored_route_geojson(data):
    points = pd.DataFrame(data)

    speed_min = points['speed_av'].min()
    speed_max = points['speed_av'].max()
    norm = mcolors.Normalize(vmin=speed_min, vmax=speed_max)
    colormap = cm.RdYlGn
    
    geojson_data = {
        "type": "FeatureCollection",
        "speed_min": speed_min,
        "speed_max": speed_max,
        "features": []
    }

    # Для каждого отрезка (между точками) добавляем его в GeoJSON
    for i in range(len(points) - 1):
        point1 = points.iloc[i]
        point2 = points.iloc[i + 1]

        # Цвет по скорости
        speed = point1['speed_av']  # Берем скорость из первой точки отрезка
        rgba = colormap(norm(speed))  # Получаем RGBA цвет
        hex_color = mcolors.to_hex(rgba)  # Преобразуем в HEX

        # Создаём GeoJSON объект для отрезка
        feature = {
            "type": "Feature",
            "properties": {
                "speed": speed,
                "color": hex_color
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [point1['lon_av'], point1['lat_av']],
                    [point2['lon_av'], point2['lat_av']]
                ]
            }
        }
        geojson_data["features"].append(feature)

    return geojson_data


@app.route("/api/getTransportFilters", methods=["GET"])
def index():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT vehicle_type, route FROM DataWithClean ORDER BY vehicle_type, route")
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]

        names = {'bus': 'Автобус', 'minibus': 'Маршрутка','tramway': 'Трамвай','trolleybus': 'Троллейбус'}

        res = dict() 
        for item in result:
            if item["vehicle_type"] not in res:
                res[item["vehicle_type"]] = dict()
                res[item["vehicle_type"]]["key"] = item["vehicle_type"]
                res[item["vehicle_type"]]["title"] = names[item["vehicle_type"]]
                res[item["vehicle_type"]]["routes"] = list()
            res[item["vehicle_type"]]["routes"].append(item["route"])
        
        AllFilters = list()
        for key in res.keys():
            AllFilters.append(res[key])

        return AllFilters

@app.route("/api/getDatesFilters", methods=["GET"])
def getDistDates():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("Select Distinct strftime('%m', signal_time) as month, strftime('%Y', signal_time) as year FROM DataWithClean")
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]

        return result
    
@app.route("/api/Filter", methods=["POST"])
def ReturnWithFilters():
    data = request.json['filter']
    settings = request.json['settings']

    st = data["timeStart"]
    et = data["timeEnd"]

    monthes = ""
    for date in data["dates"]:
        monthes+="'" + date.split("-")[1] + "', "
    monthes = monthes[:-2]
    years = ""
    for date in data["dates"]:
        years+= "'" + date.split("-")[0] + "', "
    years = years[:-2]


    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""Select strftime('%m', signal_time) as month, 
                            strftime('%Y', signal_time) as year, time(signal_time) as time, 
                            uuid, lat, lon, vehicle_type, route, speed, direction, signal_time
                            FROM DataWithClean
                            WHERE time > ? AND time < ? 
                            AND month IN ({monthes}) AND year IN ({years})          
                            ORDER BY uuid, signal_time;""", (st, et,))
        
        rows = cursor.fetchall()

        result = [dict(row) for row in rows]

        busResult = list()
        for item in result:
            if item["vehicle_type"] == "bus":
                if item["route"] in data["routes"]["bus"]:
                    busResult.append(item)
        
        tramResult = list()
        for item in result:
            if item["vehicle_type"] == "tramway":
                if item["route"] in data["routes"]["tramway"]:
                    tramResult.append(item)
        
        trolResult = list()
        for item in result:
            if item["vehicle_type"] == "trolleybus":
                if item["route"] in data["routes"]["trolleybus"]:
                    trolResult.append(item)

        miniBusResult = list()
        for item in result:
            if item["vehicle_type"] == "minibus":
                if item["route"] in data["routes"]["minibus"]:
                    miniBusResult.append(item)

        AllTransport = busResult + tramResult + trolResult + miniBusResult

        if(settings["connectToGraph"]):
            return transfer_nearest_properties(generate_geojson(AllTransport, data["colorMode"]), settings)
        else:
            return generate_geojson(AllTransport, data["colorMode"])

@app.route("/api/Stations", methods=["GET"])
def get_stations():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("Select * FROM filtered_slow_points")
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]

        return routes_near_each_point(result)

@app.route("/api/StationFilter", methods=["POST"])
def ReturnPointsWithFilters():
    # data = request.json['filter']
    data = request.json

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("Select * FROM filtered_slow_points")
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]

        busResult = list()
        for item in result:
            if item["vehicle_type"] == "bus":
                if str(item["route"]) in data["routes"]["bus"]:
                    busResult.append(item)
        
        tramResult = list()
        for item in result:
            if item["vehicle_type"] == "tramway":
                if str(item["route"]) in data["routes"]["tramway"]:
                    tramResult.append(item)
        
        trolResult = list()
        for item in result:
            if item["vehicle_type"] == "trolleybus":
                if str(item["route"]) in data["routes"]["trolleybus"]:
                    trolResult.append(item)

        miniBusResult = list()
        for item in result:
            if item["vehicle_type"] == "minibus":
                if str(item["route"]) in data["routes"]["minibus"]:
                    miniBusResult.append(item)

        AllTransport = busResult + tramResult + trolResult + miniBusResult

        return routes_near_each_point(AllTransport)

@app.route("/api/gtfs_download", methods=["GET"])
def GetArchive():
    current_script_path = __file__
    directory_path = os.path.dirname(os.path.abspath(current_script_path))
    file_path = directory_path +'/GTFS/export.zip'
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)