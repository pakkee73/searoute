ports_data = {
    "Los Angeles": {"lat": 33.716667, "lon": -118.283333},
    "Shanghai": {"lat": 31.230416, "lon": 121.473701},
    "Rotterdam": {"lat": 51.9225, "lon": 4.47917},
    "Klaipeda": {"lat": 55.703557, "lon": 21.126023}
    # 더 많은 항구 데이터를 추가할 수 있습니다.
}

def get_port_coordinates(port_name):
    port = ports_data.get(port_name)
    if port:
        return [port["lon"], port["lat"]]
    else:
        raise ValueError(f"Port '{port_name}' not found in the database")

# 예제 사용법
origin_port = "Klaipeda"
destination_port = "Los Angeles"
origin = get_port_coordinates(origin_port)
destination = get_port_coordinates(destination_port)

route = sr.searoute(origin, destination)
