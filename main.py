import sys
import os
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import re
import traceback
import json
import folium
import webbrowser


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from searoute.classes import ports, marnet, passages
from searoute.utils import get_duration, distance_length, from_nodes_edges_set, process_route, validate_lon_lat
from geojson import Feature, LineString
from functools import lru_cache
from copy import copy
from searoute.data.ports_dict import node_list
from folium.plugins import MarkerCluster

@lru_cache(maxsize=None)
def setup_P():
    from searoute.data.ports_dict import edge_list as port_e, node_list as port_n
    return from_nodes_edges_set(ports.Ports(), port_n, port_e)

@lru_cache(maxsize=None)
def setup_M():
    from searoute.data.marnet_dict import edge_list as marnet_e, node_list as marnet_n
    return from_nodes_edges_set(marnet.Marnet(), marnet_n, marnet_e)

def searoute(origin, destination, waypoints=None, units='naut', speed_knot=24, append_orig_dest=False, restrictions=[passages.Passage.northwest], include_ports=False, port_params={}, M:marnet.Marnet=None, P:ports.Ports=None, return_passages:bool = False):
    if M is None:
        M = copy(setup_M())
    if P is None:
        P = copy(setup_P())
    validate_lon_lat(origin)
    validate_lon_lat(destination)

    if waypoints is None:
        waypoints = []

    for waypoint in waypoints:
        validate_lon_lat(waypoint)

    if P is None:
        raise Exception('Ports network must not be None')

    if M is None:
        raise Exception('Marnet network must not be None')

    waypoints.insert(0, origin)
    waypoints.append(destination)

    total_length = 0
    total_duration = 0
    complete_route = []
    traversed_passages = []

    for i in range(len(waypoints) - 1):
        o_origin = tuple(waypoints[i])
        o_destination = tuple(waypoints[i+1])
        
        shortest_route_by_distance = M.shortest_path(o_origin, o_destination)

        if shortest_route_by_distance is None:
            shortest_route_by_distance = []
        
        ls, passages_in_segment = process_route(shortest_route_by_distance, M, return_passages)
        length_segment = distance_length(ls, units=units)
        duration_segment = get_duration(speed_knot, length_segment, units)

        total_length += length_segment
        total_duration += duration_segment
        complete_route.extend(ls)
        if passages_in_segment:
            traversed_passages.extend(passages_in_segment)

    feature = Feature(geometry=LineString(complete_route), properties={
                      'length': total_length, 'units': units, 'duration_hours': total_duration})

    if return_passages:
        feature.properties['traversed_passages'] = passages.Passage.filter_valid_passages(traversed_passages)

    return feature

def port_name_to_coords(port_name):
    port_name = re.sub(r'\s+', '', port_name).lower()
    for coords, port_info in node_list.items():
        if port_info['name'].replace(' ', '').lower() == port_name:
            return coords  # (경도, 위도) 순서로 반환
    raise ValueError(f"항구 이름을 찾을 수 없습니다: {port_name}")

def create_map(route, waypoints):
    # route의 좌표는 (경도, 위도) 순서입니다
    lats = [point[1] for point in route]
    lons = [point[0] for point in route]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=3)

    # 실제 해상 경로를 지도에 표시 (위도, 경도 순서로 변환)
    folium.PolyLine([(lat, lon) for lon, lat in route], color="blue", weight=2.5, opacity=1).add_to(m)

    # 출발지, 경유지, 도착지 좌표
    waypoint_coords = [port_name_to_coords(port) for port in waypoints]

    # 출발지, 경유지, 도착지에 마커와 이름 표시
    for i, (point, name) in enumerate(zip(waypoint_coords, waypoints)):
        color = 'green' if i == 0 else 'red' if i == len(waypoint_coords) - 1 else 'blue'
        folium.Marker(
            location=(point[1], point[0]),  # 위도, 경도 순서로 변경
            popup=name,
            icon=folium.Icon(color=color)
        ).add_to(m)
        folium.Tooltip(name).add_to(
            folium.CircleMarker(
                (point[1], point[0]),  # 위도, 경도 순서로 변경
                radius=5,
                color=color,
                fill=True,
                fillColor=color
            ).add_to(m)
        )

    map_file = 'route_map.html'
    m.save(map_file)
    webbrowser.open(map_file)


class SeaRouteCalculator:
    def __init__(self, master):
        self.master = master
        self.master.title("Sea Route Calculator")
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_ui()

    def setup_ui(self):
        self.master.geometry("800x600")
        self.master.minsize(800, 600)

        self.main_frame = ttk.Frame(self.master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.main_frame)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_frame = ttk.Frame(self.main_frame)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.input_frame = ttk.Frame(self.left_frame)
        self.input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.port_names = sorted([port_info['name'] for port_info in node_list.values()])
        self.port_names_normalized = {self.normalize_port_name(name): name for name in self.port_names}

        self.create_input_fields()
        self.create_buttons()

        self.waypoints_frame = ttk.LabelFrame(self.left_frame, text="경유지")
        self.waypoints_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.waypoint_entries = []

        self.result_frame = ttk.Frame(self.right_frame)
        self.result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.result_text = tk.Text(self.result_frame, wrap=tk.WORD, width=40, height=20)
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.result_scrollbar = ttk.Scrollbar(self.result_frame, orient="vertical", command=self.result_text.yview)
        self.result_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.result_text.configure(yscrollcommand=self.result_scrollbar.set)

        self.master.bind_all("<Tab>", self.focus_next_widget)

    def normalize_port_name(self, name):
        return re.sub(r'\s+', '', name.lower())

    def create_input_fields(self):
        fields = [
            ("출발지 항구 이름", "entry_origin_name"),
            ("도착지 항구 이름", "entry_destination_name"),
            ("선박 속도 (Knot)", "entry_speed", "12.50"),
            ("MFO 소모량 (톤/일)", "entry_mfo", "21.50"),
            ("MGO 소모량 (톤/일)", "entry_mgo", "2.3"),
            ("Bunker 가격 ($/톤)", "entry_bunker_price", "650")
        ]

        for i, field in enumerate(fields):
            ttk.Label(self.input_frame, text=field[0]).grid(column=0, row=i, sticky=tk.W, padx=5, pady=2)
            if field[1] in ["entry_origin_name", "entry_destination_name"]:
                setattr(self, field[1], ttk.Combobox(self.input_frame, values=self.port_names, width=30))
                combobox = getattr(self, field[1])
                combobox.bind('<KeyRelease>', self.update_combobox)
                combobox.bind("<Return>", self.focus_next_widget)
            else:
                setattr(self, field[1], ttk.Entry(self.input_frame, width=30))
                entry = getattr(self, field[1])
                entry.insert(0, field[2])  # 기본값 설정
                entry.bind("<Return>", self.focus_next_widget)
            getattr(self, field[1]).grid(column=1, row=i, sticky=(tk.W, tk.E), padx=5, pady=2)
            getattr(self, field[1]).bind("<Return>", self.focus_next_widget)

    def create_buttons(self):
        buttons_frame = ttk.Frame(self.left_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        buttons = [
            ("경유지 추가", self.add_waypoint),
            ("계산", self.calculate_route),
            ("리셋", self.reset_fields),
            ("경로 저장", self.save_route),
            ("경로 불러오기", self.load_route),
            ("다중 경로 비교", self.open_multi_route_window)
        ]

        for i, (text, command) in enumerate(buttons):
            ttk.Button(buttons_frame, text=text, command=command).grid(row=i//3, column=i%3, sticky=(tk.W, tk.E), padx=5, pady=2)

    def update_combobox(self, event):
        widget = event.widget
        value = widget.get().lower().replace(' ', '')
        data = [name for name in self.port_names if value in name.lower().replace(' ', '')]
        widget['values'] = data
        if data:
            widget.event_generate('<<ComboboxSelected>>')



    def calculate_route(self, event=None):
        try:
            waypoints = [self.entry_origin_name.get()]
            waypoints += [entry.get() for entry in self.waypoint_entries if entry.get()]
            waypoints.append(self.entry_destination_name.get())
            
            if len(waypoints) < 2:
                raise ValueError("최소한 출발지와 도착지를 입력해야 합니다.")
            
            normalized_waypoints = []
            for port in waypoints:
                normalized_port = self.normalize_port_name(port)
                if normalized_port not in self.port_names_normalized:
                    raise ValueError(f"유효하지 않은 항구 이름입니다: {port}")
                normalized_waypoints.append(self.port_names_normalized[normalized_port])

            speed_knot = float(self.entry_speed.get() or 15)
            mfo_consumption = float(self.entry_mfo.get() or 30)
            mgo_consumption = float(self.entry_mgo.get() or 2)
            bunker_price = float(self.entry_bunker_price.get() or 500)

            total_distance = 0
            total_duration = 0
            route_details = []
            complete_route = []

            for i in range(len(normalized_waypoints) - 1):
                origin = port_name_to_coords(normalized_waypoints[i])
                destination = port_name_to_coords(normalized_waypoints[i+1])
                
                print(f"Segment {i+1}: Origin: {origin}, Destination: {destination}")
                
                route = searoute(origin, destination, units='naut', speed_knot=speed_knot)
                # route.geometry['coordinates']는 (경도, 위도) 순서일 것입니다
                
                distance_nm = route.properties['length']
                duration_hours = route.properties['duration_hours']
                duration_days = duration_hours / 24
                
                total_distance += distance_nm
                total_duration += duration_hours
                
                route_details.append(f"{normalized_waypoints[i]} → {normalized_waypoints[i+1]}: {distance_nm:.1f} n.miles, {duration_days:.2f} days")
                complete_route.extend(route.geometry['coordinates'])

            total_duration_days = total_duration / 24
            mfo_cost = mfo_consumption * total_duration_days * bunker_price
            mgo_cost = mgo_consumption * total_duration_days * bunker_price
            total_cost = mfo_cost + mgo_cost

            result_text = "경로 세부 정보:\n" + "\n".join(route_details) + f"\n\n총 거리: {total_distance:.1f} n.miles\n"
            result_text += f"총 소요 시간: {total_duration_days:.2f} days\n"
            result_text += f"총 비용: ${total_cost:.2f}\n"
            result_text += f"출발지: {normalized_waypoints[0]}\n"
            result_text += f"도착지: {normalized_waypoints[-1]}"

            self.result_text.delete('1.0', tk.END)
            self.result_text.insert(tk.END, result_text)

            # 디버깅 정보
            print(f"Waypoints: {waypoints}")
            print(f"Complete route: {complete_route}")

            # 지도 생성
            create_map(complete_route, normalized_waypoints)
        except Exception as e:
            error_message = f"오류 발생: {str(e)}\n"
            error_message += f"오류 타입: {type(e).__name__}\n"
            error_message += f"오류 위치:\n{traceback.format_exc()}"
            messagebox.showerror("오류", error_message)
            print(error_message)



    def on_closing(self):
        if messagebox.askokcancel("종료", "프로그램을 종료하시겠습니까?"):
            self.master.destroy()

    def focus_next_widget(self, event):
        event.widget.tk_focusNext().focus()
        return "break"

    def add_waypoint(self, event=None):
        waypoint_frame = ttk.Frame(self.waypoints_frame)
        waypoint_frame.pack(fill=tk.X, padx=5, pady=2)
        
        waypoint_entry = ttk.Combobox(waypoint_frame, values=self.port_names, width=30)
        waypoint_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        waypoint_entry.bind('<KeyRelease>', self.update_combobox)
        waypoint_entry.bind("<Return>", self.on_waypoint_enter)
        
        remove_button = ttk.Button(waypoint_frame, text="삭제", command=lambda: self.remove_waypoint(waypoint_frame, waypoint_entry))
        remove_button.pack(side=tk.RIGHT)
        
        self.waypoint_entries.append(waypoint_entry)
        
        waypoint_entry.focus()


    def on_waypoint_enter(self, event):
        if event.widget.get().strip():
            self.add_waypoint()
        else:
            event.widget.tk_focusNext().focus()
        return "break"

    def remove_waypoint(self, frame, entry):
        frame.destroy()
        if entry in self.waypoint_entries:
            self.waypoint_entries.remove(entry)

    def reset_fields(self):
        self.entry_origin_name.set('')
        self.entry_destination_name.set('')
        self.entry_speed.delete(0, tk.END)
        self.entry_speed.insert(0, "12.50")
        self.entry_mfo.delete(0, tk.END)
        self.entry_mfo.insert(0, "21.50")
        self.entry_mgo.delete(0, tk.END)
        self.entry_mgo.insert(0, "2.3")
        self.entry_bunker_price.delete(0, tk.END)
        self.entry_bunker_price.insert(0, "650")
        for entry in self.waypoint_entries:
            entry.master.destroy()
        self.waypoint_entries.clear()
        self.result_text.delete('1.0', tk.END)

    def save_route(self):
        route_data = {
            "origin": self.entry_origin_name.get(),
            "destination": self.entry_destination_name.get(),
            "waypoints": [entry.get() for entry in self.waypoint_entries],
            "speed": self.entry_speed.get(),
            "mfo_consumption": self.entry_mfo.get(),
            "mgo_consumption": self.entry_mgo.get(),
            "bunker_price": self.entry_bunker_price.get()
        }
        
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "w") as f:
                json.dump(route_data, f)

    def load_route(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "r") as f:
                route_data = json.load(f)
            
            self.entry_origin_name.set(route_data["origin"])
            self.entry_destination_name.set(route_data["destination"])
            self.entry_speed.delete(0, tk.END)
            self.entry_speed.insert(0, route_data["speed"])
            self.entry_mfo.delete(0, tk.END)
            self.entry_mfo.insert(0, route_data["mfo_consumption"])
            self.entry_mgo.delete(0, tk.END)
            self.entry_mgo.insert(0, route_data["mgo_consumption"])
            self.entry_bunker_price.delete(0, tk.END)
            self.entry_bunker_price.insert(0, route_data["bunker_price"])
            
            for entry in self.waypoint_entries:
                entry.master.destroy()
            self.waypoint_entries.clear()
            
            for waypoint in route_data["waypoints"]:
                self.add_waypoint()
                self.waypoint_entries[-1].set(waypoint)

    def open_multi_route_window(self):
        multi_window = tk.Toplevel(self.master)
        multi_window.title("다중 경로 비교")
        multi_window.geometry("600x400")

        routes_frame = ttk.Frame(multi_window, padding="10")
        routes_frame.pack(fill=tk.BOTH, expand=True)

        routes = []
        for i in range(3):  # 3개의 경로 비교
            route_frame = ttk.LabelFrame(routes_frame, text=f"경로 {i+1}")
            route_frame.pack(fill=tk.X, padx=5, pady=5)

            ttk.Label(route_frame, text="출발지").grid(row=0, column=0, sticky=tk.W)
            origin = ttk.Combobox(route_frame, values=self.port_names)
            origin.grid(row=0, column=1, sticky=(tk.W, tk.E))

            ttk.Label(route_frame, text="도착지").grid(row=1, column=0, sticky=tk.W)
            destination = ttk.Combobox(route_frame, values=self.port_names)
            destination.grid(row=1, column=1, sticky=(tk.W, tk.E))

            routes.append((origin, destination))

        def compare_routes():
            results = []
            for origin, destination in routes:
                try:
                    origin_normalized = self.port_names_normalized[self.normalize_port_name(origin.get())]
                    destination_normalized = self.port_names_normalized[self.normalize_port_name(destination.get())]
                    origin_coords = port_name_to_coords(origin_normalized)
                    destination_coords = port_name_to_coords(destination_normalized)
                    route = searoute(origin_coords, destination_coords)
                    distance_nm = route.properties['length']
                    duration_hours = route.properties['duration_hours']
                    duration_days = duration_hours / 24
                    results.append(f"{origin_normalized} → {destination_normalized}: {distance_nm:.1f} n.miles, {duration_days:.2f} days")
                except Exception as e:
                    results.append(str(e))

            result_window = tk.Toplevel(multi_window)
            result_window.title("경로 비교 결과")
            result_window.geometry("400x300")
            
            result_frame = ttk.Frame(result_window, padding="10")
            result_frame.pack(fill=tk.BOTH, expand=True)

            result_text = tk.Text(result_frame, wrap=tk.WORD)
            result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            result_scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=result_text.yview)
            result_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            result_text.configure(yscrollcommand=result_scrollbar.set)

            for i, result in enumerate(results):
                result_text.insert(tk.END, f"경로 {i+1}:\n{result}\n\n")

        ttk.Button(multi_window, text="경로 비교", command=compare_routes).pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = SeaRouteCalculator(root)
    root.mainloop()
