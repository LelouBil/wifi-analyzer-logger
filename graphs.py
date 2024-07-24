import pandas as pd
import sys

from bokeh.io import show, export_png
from bokeh.plotting import gmap
from bokeh.models import GMapOptions, ColumnDataSource
from bokeh.models import ColumnDataSource, ColorBar
from bokeh.transform import linear_cmap
from bokeh.palettes import Plasma256, RdYlGn, Turbo256

import matplotlib.pyplot as plt

maps_api = "AIzaSyBFvtZKLDQltqjfhR-t4MU-DZF3Sy1U4gw"

map_styles = [
    {
        "featureType": "poi",
        "elementType": "all",
        "stylers": [{"visibility": "off"}]
    },
    {
        "featureType": "transit",
        "elementType": "all",
        "stylers": [{"visibility": "off"}]
    }
]


def plot_devices_count(df, lat, lng, zoom=17, map_type='roadmap', name=None):
    gmap_options = GMapOptions(lat=lat, lng=lng, 
                               map_type=map_type, zoom=zoom)
    p = gmap(maps_api, gmap_options, title='Number of hotspots in the center of Zagreb', 
             width=1300, height=900,tools=['hover', 'reset', 'wheel_zoom', 'pan'])
    
    source = ColumnDataSource(df)
    mapper = linear_cmap("devices_count",Turbo256,50,100)
    center = p.scatter(color=mapper,x="longitude", y="latitude", source=source, marker="circle", size=15)
    color_bar = ColorBar(color_mapper=mapper['transform'],location=(0,0))
    p.add_layout(color_bar,'right')
    show(p)
    if name:
        export_png(p, filename=name)
    return p

def plot_used_channels(df, lat, lng, zoom=17, map_type='roadmap', name=None):
    gmap_options = GMapOptions(lat=lat, lng=lng, 
                               map_type=map_type, zoom=zoom)
    p = gmap(maps_api, gmap_options, title='Most used channels in the center of Zagreb', 
             width=1300, height=900,tools=['hover', 'reset', 'wheel_zoom', 'pan'])
    
    df['index'] = df.index.astype(str)  # Add index as a column and convert to string for legend
    df["most_used_channel"] = df["most_used_channel"].astype(str)
    source = ColumnDataSource(df)
    mapper = linear_cmap("most_used_channel", Turbo256, 0, 150)
    
    center = p.scatter(color=mapper, x="longitude", y="latitude", legend_field="most_used_channel", source=source, marker="circle", size=15)
    p.legend.title = 'Most used channels'
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"  # Optionally, allow hiding points by clicking legend

    show(p)
    if name:
        export_png(p, filename=name)
    return p


def print_list(lst):
    print(lst)
    for i in lst:
        print(i)


def heatmap_nb_spots(df, export=False):

    locdf = pd.DataFrame(df.location.values.tolist())
    df["longitude"] = locdf.longitude
    df["latitude"] = locdf.latitude
    del df["location"]
    df["devices_count"] = df.device.map(lambda x: len(x))

    if export:
        plot_devices_count(df, lat=45.811467, lng=15.976145, name="heatmap_nb_hotspots.png")
    else:
        plot_devices_count(df, lat=45.811467, lng=15.976145)


def most_used_channel(li):
    tab = {}
    for dic in li:
        if dic["CHAN"] not in list(tab.keys()):
            tab[dic["CHAN"]] = 1
        else:
            tab[dic["CHAN"]] += 1
    return max(tab, key=tab.get)



def heatmap_channels_points(df, export=False):
    locdf = pd.DataFrame(df.location.values.tolist())
    df["longitude"] = locdf.longitude
    df["latitude"] = locdf.latitude
    del df["location"]
    df["most_used_channel"] = df.device.map(lambda x: most_used_channel(x))

    plot_used_channels(df, lat=45.811467, lng=15.976145)

def speed_mean(li):
    if len(li["iperf_default"]) == 0 or len(li["iperf_reversed"]) == 0:
        return 0
    return ((li["iperf_default"][0]["iperf_bandwidth_kbits_sec"] + li["iperf_reversed"][0]["iperf_bandwidth_kbits_sec"]) / 2) / 1000

def heatmap_speed_points(df_speed, export=False):
    locdf = pd.DataFrame(df_speed.location.values.tolist())
    df_speed["longitude"] = locdf.longitude
    df_speed["latitude"] = locdf.latitude
    del df_speed["location"]

    df_speed["speed"] = df_speed.speed_info.map(lambda x: speed_mean(x))

    # Plotting

    gmap_options = GMapOptions(lat=45.811467, lng=15.976145, 
                               map_type='roadmap', zoom=17)
    p = gmap(maps_api, gmap_options, title='Speed in the center of Zagreb', 
             width=1300, height=900,tools=['hover', 'reset', 'wheel_zoom', 'pan'])
    
    source = ColumnDataSource(df_speed)
    mapper = linear_cmap("speed", Turbo256, 0, 50)
    center = p.scatter(color=mapper, x="longitude", y="latitude", source=source, marker="circle", size=15)
    color_bar = ColorBar(color_mapper=mapper['transform'],location=(0,0))
    p.add_layout(color_bar,'right')
    show(p)
    if export:
        export_png(p, filename="heatmap_speed.png")
    return p



def plot_speed_nb_hotspots(df, df_speed):
    locdf = pd.DataFrame(df.location.values.tolist())
    df["longitude"] = locdf.longitude
    df["latitude"] = locdf.latitude
    del df["location"]
    df["timestamp"] = df["timestamp"].dt.floor('Min')
    df["devices_count"] = df.device.map(lambda x: len(x))

    locdf = pd.DataFrame(df_speed.location.values.tolist())
    df_speed["longitude"] = locdf.longitude
    df_speed["latitude"] = locdf.latitude
    del df_speed["location"]
    

    df_speed["speed"] = df_speed.speed_info.map(lambda x: speed_mean(x))
    df_speed["timestamp"] = df_speed["timestamp"].dt.floor('Min')
    del df_speed["speed_info"]


    merged_df = pd.merge(df, df_speed, on=['timestamp']) #latitude_x & longitude_x are the latitude and longitude of df, the phone taking measurements
    del merged_df["latitude_y"]
    del merged_df["longitude_y"]

    fig, ax = plt.subplots(1)
    ax.scatter(merged_df["devices_count"], merged_df["speed"], label="Number of hotspots")
    ax.set_xlabel("Number of hotspots")
    ax.set_ylabel("Speed (Mbit/s)")
    ax.set_title("Speed and number of hotspots in the center of Zagreb")

    plt.show()

    return


def latency_mean(li):
    sum = 0
    index = 0
    for dic in li["ping_runs"]:
        sum += dic["ping_time_ms"]
        index +=1
    return sum/index


def plot_latency_nb_hotspots(df, df_speed):
    locdf = pd.DataFrame(df.location.values.tolist())
    df["longitude"] = locdf.longitude
    df["latitude"] = locdf.latitude
    del df["location"]
    df["timestamp"] = df["timestamp"].dt.floor('Min')
    df["devices_count"] = df.device.map(lambda x: len(x))

    locdf = pd.DataFrame(df_speed.location.values.tolist())
    df_speed["longitude"] = locdf.longitude
    df_speed["latitude"] = locdf.latitude
    del df_speed["location"]
    

    df_speed["latency"] = df_speed.speed_info.map(lambda x: latency_mean(x))
    df_speed["timestamp"] = df_speed["timestamp"].dt.floor('Min')
    del df_speed["speed_info"]


    merged_df = pd.merge(df, df_speed, on=['timestamp']) #latitude_x & longitude_x are the latitude and longitude of df, the phone taking measurements
    del merged_df["latitude_y"]
    del merged_df["longitude_y"]


    # Plotting

    fig, ax = plt.subplots(1)
    ax.scatter(merged_df["devices_count"], merged_df["latency"], label="Number of hotspots")
    ax.set_xlabel("Number of hotspots")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency and number of hotspots in the center of Zagreb")



    plt.show()


def main():
    df = pd.read_json("signal-recording.json") # sys.argv[1]
    df_speed = pd.read_json("speed-recording.json")


    # Uncomment the function you want to run

    heatmap_nb_spots(df)
    #heatmap_channels_points(df)
    #heatmap_speed_points(df_speed)
    #plot_speed_nb_hotspots(df, df_speed)
    #plot_latency_nb_hotspots(df, df_speed)
    

if __name__ == "__main__":
    main()