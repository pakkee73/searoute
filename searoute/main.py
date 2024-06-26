import sys
import os
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import re
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from searoute.classes import ports, marnet, passages
from searoute.utils import get_duration, distance_length, from_nodes_edges_set, process_route, validate_lon_lat
from geojson import Feature, LineString
from functools import lru_cache
from copy import copy
from searoute.data.ports_dict import node_list

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
            return [port_info['x'], port_info['y']]
    raise ValueError("항구 이름을 찾을 수 없습니다: {}".format(port_name))

def calculate_route(event=None):
    try:
        waypoints = [entry_origin_name.get()] + [entry.get() for entry in waypoint_entries if entry.get()] + [entry_destination_name.get()]
        
        if len(waypoints) < 2:
            raise ValueError("최소한 출발지와 도착지를 입력해야 합니다.")
        
        speed_knot = float(entry_speed.get())
        mfo_consumption = float(entry_mfo.get())
        mgo_consumption = float(entry_mgo.get())
        bunker_price = float(entry_bunker_price.get())

        total_distance = 0
        total_duration = 0
        route_details = []

        for i in range(len(waypoints) - 1):
            origin = port_name_to_coords(waypoints[i])
            destination = port_name_to_coords(waypoints[i+1])
            
            print(f"Segment {i+1}: Origin: {origin}, Destination: {destination}")  # 디버깅용 출력
            
            route = searoute(origin, destination, units='naut', speed_knot=speed_knot)
            
            distance_nm = route.properties['length']
            duration_hours = route.properties['duration_hours']
            duration_days = duration_hours / 24  # 시간을 일로 변환
            
            total_distance += distance_nm
            total_duration += duration_hours
            
            route_details.append(f"{waypoints[i]} → {waypoints[i+1]}: {distance_nm:.1f} n.miles, {duration_days:.2f} days")

        total_duration_days = total_duration / 24
        mfo_cost = mfo_consumption * total_duration_days * bunker_price
        mgo_cost = mgo_consumption * total_duration_days * bunker_price
        total_cost = mfo_cost + mgo_cost

        result_text = "경로 세부 정보:\n" + "\n".join(route_details) + f"\n\n총 거리: {total_distance:.1f} n.miles\n"
        result_text += f"총 소요 시간: {total_duration_days:.2f} days\n"
        result_text += f"총 비용: ${total_cost:.2f}\n"
        result_text += f"출발지: {waypoints[0]}\n"
        result_text += f"도착지: {waypoints[-1]}"

        result.set(result_text)
    except Exception as e:
        error_message = f"오류 발생: {str(e)}\n"
        error_message += f"오류 타입: {type(e).__name__}\n"
        error_message += f"오류 위치:\n{traceback.format_exc()}"
        messagebox.showerror("오류", error_message)
        print(error_message)  # 콘솔에도 오류 메시지 출력

def reset_fields():
    entry_origin_name.delete(0, tk.END)
    entry_destination_name.delete(0, tk.END)
    entry_speed.delete(0, tk.END)
    entry_mfo.delete(0, tk.END)
    entry_mgo.delete(0, tk.END)
    entry_bunker_price.delete(0, tk.END)
    for entry in waypoint_entries:
        entry.master.destroy()
    waypoint_entries.clear()
    result.set("")

waypoint_entries = []

def add_waypoint(event=None):
    waypoint_frame = ttk.Frame(waypoints_frame)
    waypoint_frame.pack(fill=tk.X, padx=5, pady=2)
    
    waypoint_entry = ttk.Entry(waypoint_frame)
    waypoint_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
    waypoint_entry.bind("<Return>", on_waypoint_enter)
    
    remove_button = ttk.Button(waypoint_frame, text="삭제", command=lambda: remove_waypoint(waypoint_frame, waypoint_entry))
    remove_button.pack(side=tk.RIGHT)
    
    waypoint_entries.append(waypoint_entry)
    
    waypoint_entry.focus()  # 새로 추가된 입력 칸에 포커스 설정

def on_waypoint_enter(event):
    if event.widget.get().strip():
        add_waypoint()
    else:
        event.widget.tk_focusNext().focus()
    return "break"

def remove_waypoint(frame, entry):
    frame.destroy()
    if entry in waypoint_entries:
        waypoint_entries.remove(entry)

def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
    return "break"

app = tk.Tk()
app.title("Sea Route Calculator")
app.protocol("WM_DELETE_WINDOW", app.destroy)  # Close the app properly

main_frame = ttk.Frame(app, padding="10")
main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

input_frame = ttk.Frame(main_frame)
input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

ttk.Label(input_frame, text="출발지 항구 이름").grid(column=0, row=0, sticky=tk.W)
entry_origin_name = ttk.Entry(input_frame)
entry_origin_name.grid(column=1, row=0, sticky=(tk.W, tk.E))
entry_origin_name.bind("<Return>", focus_next_widget)

ttk.Label(input_frame, text="도착지 항구 이름").grid(column=0, row=1, sticky=tk.W)
entry_destination_name = ttk.Entry(input_frame)
entry_destination_name.grid(column=1, row=1, sticky=(tk.W, tk.E))
entry_destination_name.bind("<Return>", focus_next_widget)

ttk.Label(input_frame, text="선박 속도 (Knot)").grid(column=0, row=2, sticky=tk.W)
entry_speed = ttk.Entry(input_frame)
entry_speed.grid(column=1, row=2, sticky=(tk.W, tk.E))
entry_speed.bind("<Return>", focus_next_widget)

ttk.Label(input_frame, text="MFO 소모량 (톤/일)").grid(column=0, row=3, sticky=tk.W)
entry_mfo = ttk.Entry(input_frame)
entry_mfo.grid(column=1, row=3, sticky=(tk.W, tk.E))
entry_mfo.bind("<Return>", focus_next_widget)

ttk.Label(input_frame, text="MGO 소모량 (톤/일)").grid(column=0, row=4, sticky=tk.W)
entry_mgo = ttk.Entry(input_frame)
entry_mgo.grid(column=1, row=4, sticky=(tk.W, tk.E))
entry_mgo.bind("<Return>", focus_next_widget)

ttk.Label(input_frame, text="Bunker 가격 ($/톤)").grid(column=0, row=5, sticky=tk.W)
entry_bunker_price = ttk.Entry(input_frame)
entry_bunker_price.grid(column=1, row=5, sticky=(tk.W, tk.E))
entry_bunker_price.bind("<Return>", focus_next_widget)

waypoints_frame = ttk.LabelFrame(main_frame, text="경유지")
waypoints_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

ttk.Button(main_frame, text="경유지 추가", command=add_waypoint).grid(row=2, column=0, sticky=(tk.W, tk.E))

ttk.Button(main_frame, text="계산", command=calculate_route).grid(row=3, column=0, sticky=(tk.W, tk.E))

reset_button = ttk.Button(main_frame, text="리셋", command=reset_fields)
reset_button.grid(row=4, column=0, sticky=(tk.W, tk.E))

result = tk.StringVar()
result_label = ttk.Label(main_frame, textvariable=result, wraplength=400)
result_label.grid(row=5, column=0, sticky=(tk.W, tk.E))

for child in main_frame.winfo_children():
    child.grid_configure(padx=5, pady=5)

app.bind_all("<Tab>", focus_next_widget)

app.mainloop()