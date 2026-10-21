import math
import logging
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests

from app.database import get_geoguessr_google_usage, reserve_geoguessr_google_usage

ROUND_COUNT = 5
ROOM_ROUND_TIME_LIMIT_SECONDS = 20
MAX_PLAYERS = 8
MAX_SCORE_PER_ROUND = 5_000
EARTH_RADIUS_KM = 6_371.0088
GEOGUESSR_REGIONS = {"france", "europe", "world"}
GEOGUESSR_VARIANTS = {"cities", "panorama"}
MAPILLARY_API_URL = "https://graph.mapillary.com/images"
GOOGLE_STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
GOOGLE_STREETVIEW_MONTHLY_LIMIT = 4_000
logger = logging.getLogger("pedantix.geoguessr")

# Curated city coordinates keep rounds deterministic in format and avoid geocoding
# dependencies; the answer is only exposed after a guess is locked.
CITY_LOCATIONS = (
    ("Paris", "France", "france", 48.8566, 2.3522),
    ("Lyon", "France", "france", 45.7640, 4.8357),
    ("Marseille", "France", "france", 43.2965, 5.3698),
    ("Toulouse", "France", "france", 43.6047, 1.4442),
    ("Bordeaux", "France", "france", 44.8378, -0.5792),
    ("Lille", "France", "france", 50.6292, 3.0573),
    ("Nantes", "France", "france", 47.2184, -1.5536),
    ("Strasbourg", "France", "france", 48.5734, 7.7521),
    ("Nice", "France", "france", 43.7102, 7.2620),
    ("Rennes", "France", "france", 48.1173, -1.6778),
    ("Montpellier", "France", "france", 43.6119, 3.8772),
    ("Grenoble", "France", "france", 45.1885, 5.7245),
    ("Dijon", "France", "france", 47.3220, 5.0415),
    ("Reims", "France", "france", 49.2583, 4.0317),
    ("Clermont-Ferrand", "France", "france", 45.7772, 3.0870),
    ("Brest", "France", "france", 48.3904, -4.4861),
    ("Ajaccio", "France", "france", 41.9192, 8.7386),
    ("Angers", "France", "france", 47.4784, -0.5632),
    ("Nîmes", "France", "france", 43.8367, 4.3601),
    ("Le Mans", "France", "france", 48.0061, 0.1996),
    ("Tours", "France", "france", 47.3941, 0.6848),
    ("Amiens", "France", "france", 49.8941, 2.2958),
    ("Limoges", "France", "france", 45.8336, 1.2611),
    ("Perpignan", "France", "france", 42.6887, 2.8948),
    ("Metz", "France", "france", 49.1193, 6.1757),
    ("Nancy", "France", "france", 48.6921, 6.1844),
    ("Caen", "France", "france", 49.1829, -0.3707),
    ("Orléans", "France", "france", 47.9029, 1.9093),
    ("Mulhouse", "France", "france", 47.7508, 7.3359),
    ("Rouen", "France", "france", 49.4432, 1.0993),
    ("Saint-Étienne", "France", "france", 45.4397, 4.3872),
    ("Toulon", "France", "france", 43.1242, 5.9280),
    ("La Rochelle", "France", "france", 46.1603, -1.1511),
    ("Annecy", "France", "france", 45.8992, 6.1294),
    ("Chambéry", "France", "france", 45.5646, 5.9178),
    ("Bayonne", "France", "france", 43.4929, -1.4748),
    ("Avignon", "France", "france", 43.9493, 4.8055),
    ("Pau", "France", "france", 43.2951, -0.3708),
    ("Poitiers", "France", "france", 46.5802, 0.3404),
    ("Besançon", "France", "france", 47.2378, 6.0241),
    ("Quimper", "France", "france", 47.9960, -4.1024),
    ("Vannes", "France", "france", 47.6582, -2.7608),
    ("Colmar", "France", "france", 48.0794, 7.3585),
    ("Dunkerque", "France", "france", 51.0344, 2.3768),
    ("Valence", "France", "france", 44.9334, 4.8924),
    ("Blois", "France", "france", 47.5861, 1.3359),
    ("Bourges", "France", "france", 47.0810, 2.3988),
    ("Lorient", "France", "france", 47.7483, -3.3702),
    ("Tarbes", "France", "france", 43.2328, 0.0781),
    ("Amsterdam", "Pays-Bas", "europe", 52.3676, 4.9041),
    ("Bruxelles", "Belgique", "europe", 50.8503, 4.3517),
    ("Londres", "Royaume-Uni", "europe", 51.5072, -0.1276),
    ("Dublin", "Irlande", "europe", 53.3498, -6.2603),
    ("Lisbonne", "Portugal", "europe", 38.7223, -9.1393),
    ("Madrid", "Espagne", "europe", 40.4168, -3.7038),
    ("Barcelone", "Espagne", "europe", 41.3874, 2.1686),
    ("Rome", "Italie", "europe", 41.9028, 12.4964),
    ("Milan", "Italie", "europe", 45.4642, 9.1900),
    ("Berlin", "Allemagne", "europe", 52.5200, 13.4050),
    ("Munich", "Allemagne", "europe", 48.1351, 11.5820),
    ("Vienne", "Autriche", "europe", 48.2082, 16.3738),
    ("Prague", "Tchéquie", "europe", 50.0755, 14.4378),
    ("Varsovie", "Pologne", "europe", 52.2297, 21.0122),
    ("Budapest", "Hongrie", "europe", 47.4979, 19.0402),
    ("Athènes", "Grèce", "europe", 37.9838, 23.7275),
    ("Stockholm", "Suède", "europe", 59.3293, 18.0686),
    ("Oslo", "Norvège", "europe", 59.9139, 10.7522),
    ("Helsinki", "Finlande", "europe", 60.1699, 24.9384),
    ("Copenhague", "Danemark", "europe", 55.6761, 12.5683),
    ("Bucarest", "Roumanie", "europe", 44.4268, 26.1025),
    ("Istanbul", "Turquie", "europe", 41.0082, 28.9784),
    ("Reykjavik", "Islande", "europe", 64.1466, -21.9426),
    ("Séville", "Espagne", "europe", 37.3891, -5.9845),
    ("Valence", "Espagne", "europe", 39.4699, -0.3763),
    ("Saragosse", "Espagne", "europe", 41.6488, -0.8891),
    ("Málaga", "Espagne", "europe", 36.7213, -4.4214),
    ("Bilbao", "Espagne", "europe", 43.2630, -2.9350),
    ("Porto", "Portugal", "europe", 41.1579, -8.6291),
    ("Florence", "Italie", "europe", 43.7696, 11.2558),
    ("Naples", "Italie", "europe", 40.8518, 14.2681),
    ("Turin", "Italie", "europe", 45.0703, 7.6869),
    ("Venise", "Italie", "europe", 45.4408, 12.3155),
    ("Hambourg", "Allemagne", "europe", 53.5511, 9.9937),
    ("Francfort", "Allemagne", "europe", 50.1109, 8.6821),
    ("Cologne", "Allemagne", "europe", 50.9375, 6.9603),
    ("Zurich", "Suisse", "europe", 47.3769, 8.5417),
    ("Genève", "Suisse", "europe", 46.2044, 6.1432),
    ("Cracovie", "Pologne", "europe", 50.0647, 19.9450),
    ("Gdańsk", "Pologne", "europe", 54.3520, 18.6466),
    ("Belgrade", "Serbie", "europe", 44.7866, 20.4489),
    ("Sofia", "Bulgarie", "europe", 42.6977, 23.3219),
    ("Zagreb", "Croatie", "europe", 45.8150, 15.9819),
    ("Ljubljana", "Slovénie", "europe", 46.0569, 14.5058),
    ("Tallinn", "Estonie", "europe", 59.4370, 24.7536),
    ("Riga", "Lettonie", "europe", 56.9496, 24.1052),
    ("Vilnius", "Lituanie", "europe", 54.6872, 25.2797),
    ("Gothenburg", "Suède", "europe", 57.7089, 11.9746),
    ("Bergen", "Norvège", "europe", 60.3913, 5.3221),
    ("Malmö", "Suède", "europe", 55.6050, 13.0038),
    ("Rotterdam", "Pays-Bas", "europe", 51.9244, 4.4777),
    ("Anvers", "Belgique", "europe", 51.2194, 4.4025),
    ("Manchester", "Royaume-Uni", "europe", 53.4808, -2.2426),
    ("Édimbourg", "Royaume-Uni", "europe", 55.9533, -3.1883),
    ("Bristol", "Royaume-Uni", "europe", 51.4545, -2.5879),
    ("Thessalonique", "Grèce", "europe", 40.6401, 22.9444),
    ("New York", "États-Unis", "world", 40.7128, -74.0060),
    ("Los Angeles", "États-Unis", "world", 34.0522, -118.2437),
    ("Chicago", "États-Unis", "world", 41.8781, -87.6298),
    ("Mexico", "Mexique", "world", 19.4326, -99.1332),
    ("La Havane", "Cuba", "world", 23.1136, -82.3666),
    ("Bogotá", "Colombie", "world", 4.7110, -74.0721),
    ("Lima", "Pérou", "world", -12.0464, -77.0428),
    ("Rio de Janeiro", "Brésil", "world", -22.9068, -43.1729),
    ("Buenos Aires", "Argentine", "world", -34.6037, -58.3816),
    ("Santiago", "Chili", "world", -33.4489, -70.6693),
    ("Tokyo", "Japon", "world", 35.6762, 139.6503),
    ("Osaka", "Japon", "world", 34.6937, 135.5023),
    ("Séoul", "Corée du Sud", "world", 37.5665, 126.9780),
    ("Pékin", "Chine", "world", 39.9042, 116.4074),
    ("Shanghai", "Chine", "world", 31.2304, 121.4737),
    ("Bangkok", "Thaïlande", "world", 13.7563, 100.5018),
    ("Hanoï", "Vietnam", "world", 21.0278, 105.8342),
    ("Singapour", "Singapour", "world", 1.3521, 103.8198),
    ("Jakarta", "Indonésie", "world", -6.2088, 106.8456),
    ("Delhi", "Inde", "world", 28.6139, 77.2090),
    ("Mumbai", "Inde", "world", 19.0760, 72.8777),
    ("Katmandou", "Népal", "world", 27.7172, 85.3240),
    ("Dubaï", "Émirats arabes unis", "world", 25.2048, 55.2708),
    ("Le Caire", "Égypte", "world", 30.0444, 31.2357),
    ("Nairobi", "Kenya", "world", -1.2921, 36.8219),
    ("Johannesburg", "Afrique du Sud", "world", -26.2041, 28.0473),
    ("Le Cap", "Afrique du Sud", "world", -33.9249, 18.4241),
    ("Casablanca", "Maroc", "world", 33.5731, -7.5898),
    ("Sydney", "Australie", "world", -33.8688, 151.2093),
    ("Melbourne", "Australie", "world", -37.8136, 144.9631),
    ("Auckland", "Nouvelle-Zélande", "world", -36.8509, 174.7645),
    ("Montréal", "Canada", "world", 45.5019, -73.5674),
    ("Toronto", "Canada", "world", 43.6532, -79.3832),
    ("Vancouver", "Canada", "world", 49.2827, -123.1207),
    ("Québec", "Canada", "world", 46.8139, -71.2080),
    ("Boston", "États-Unis", "world", 42.3601, -71.0589),
    ("Seattle", "États-Unis", "world", 47.6062, -122.3321),
    ("San Francisco", "États-Unis", "world", 37.7749, -122.4194),
    ("Miami", "États-Unis", "world", 25.7617, -80.1918),
    ("Denver", "États-Unis", "world", 39.7392, -104.9903),
    ("Portland", "États-Unis", "world", 45.5152, -122.6784),
    ("La Nouvelle-Orléans", "États-Unis", "world", 29.9511, -90.0715),
    ("Guadalajara", "Mexique", "world", 20.6597, -103.3496),
    ("Oaxaca", "Mexique", "world", 17.0732, -96.7266),
    ("Puebla", "Mexique", "world", 19.0414, -98.2063),
    ("Medellín", "Colombie", "world", 6.2476, -75.5658),
    ("Carthagène", "Colombie", "world", 10.3910, -75.4794),
    ("Quito", "Équateur", "world", -0.1807, -78.4678),
    ("Cusco", "Pérou", "world", -13.5320, -71.9675),
    ("Montevideo", "Uruguay", "world", -34.9011, -56.1645),
    ("Salvador", "Brésil", "world", -12.9777, -38.5016),
    ("Recife", "Brésil", "world", -8.0476, -34.8770),
    ("Brasília", "Brésil", "world", -15.7975, -47.8919),
    ("La Paz", "Bolivie", "world", -16.4897, -68.1193),
    ("San José", "Costa Rica", "world", 9.9281, -84.0907),
    ("Panama", "Panama", "world", 8.9824, -79.5199),
    ("Marrakech", "Maroc", "world", 31.6295, -7.9811),
    ("Tunis", "Tunisie", "world", 36.8065, 10.1815),
    ("Dakar", "Sénégal", "world", 14.7167, -17.4677),
    ("Accra", "Ghana", "world", 5.6037, -0.1870),
    ("Lagos", "Nigeria", "world", 6.5244, 3.3792),
    ("Abuja", "Nigeria", "world", 9.0765, 7.3986),
    ("Addis-Abeba", "Éthiopie", "world", 8.9806, 38.7578),
    ("Kigali", "Rwanda", "world", -1.9441, 30.0619),
    ("Dar es Salaam", "Tanzanie", "world", -6.7924, 39.2083),
    ("Maputo", "Mozambique", "world", -25.9692, 32.5732),
    ("Lusaka", "Zambie", "world", -15.3875, 28.3228),
    ("Amman", "Jordanie", "world", 31.9539, 35.9106),
    ("Beyrouth", "Liban", "world", 33.8938, 35.5018),
    ("Tel-Aviv", "Israël", "world", 32.0853, 34.7818),
    ("Riyad", "Arabie saoudite", "world", 24.7136, 46.6753),
    ("Doha", "Qatar", "world", 25.2854, 51.5310),
    ("Mascate", "Oman", "world", 23.5880, 58.3829),
    ("Tbilissi", "Géorgie", "world", 41.7151, 44.8271),
    ("Almaty", "Kazakhstan", "world", 43.2220, 76.8512),
    ("Tachkent", "Ouzbékistan", "world", 41.2995, 69.2401),
    ("Karachi", "Pakistan", "world", 24.8607, 67.0011),
    ("Lahore", "Pakistan", "world", 31.5204, 74.3587),
    ("Dhaka", "Bangladesh", "world", 23.8103, 90.4125),
    ("Colombo", "Sri Lanka", "world", 6.9271, 79.8612),
    ("Kuala Lumpur", "Malaisie", "world", 3.1390, 101.6869),
    ("Manille", "Philippines", "world", 14.5995, 120.9842),
    ("Cebu", "Philippines", "world", 10.3157, 123.8854),
    ("Chiang Mai", "Thaïlande", "world", 18.7883, 98.9853),
    ("Phnom Penh", "Cambodge", "world", 11.5564, 104.9282),
    ("Yangon", "Myanmar", "world", 16.8409, 96.1735),
    ("Taipei", "Taïwan", "world", 25.0330, 121.5654),
    ("Hong Kong", "Chine", "world", 22.3193, 114.1694),
    ("Nagoya", "Japon", "world", 35.1815, 136.9066),
    ("Fukuoka", "Japon", "world", 33.5904, 130.4017),
    ("Busan", "Corée du Sud", "world", 35.1796, 129.0756),
    ("Chengdu", "Chine", "world", 30.5728, 104.0668),
    ("Xi'an", "Chine", "world", 34.3416, 108.9398),
    ("Chongqing", "Chine", "world", 29.4316, 106.9123),
    ("Perth", "Australie", "world", -31.9505, 115.8605),
    ("Brisbane", "Australie", "world", -27.4698, 153.0251),
    ("Adélaïde", "Australie", "world", -34.9285, 138.6007),
    ("Wellington", "Nouvelle-Zélande", "world", -41.2866, 174.7756),
    ("Christchurch", "Nouvelle-Zélande", "world", -43.5321, 172.6362),
)

# Population estimates are for the city or its continuous urban area. Keeping them
# with the curated coordinates makes each region's minimum population explicit.
CITY_ADDITIONS = (
    ("Le Havre", "France", "france", 49.4944, 0.1079, 166_000),
    ("Roubaix", "France", "france", 50.6942, 3.1746, 98_000),
    ("Tourcoing", "France", "france", 50.7239, 3.1612, 98_000),
    ("Saint-Denis", "France", "france", 48.9362, 2.3574, 113_000),
    ("Montreuil", "France", "france", 48.8638, 2.4485, 111_000),
    ("Argenteuil", "France", "france", 48.9472, 2.2467, 110_000),
    ("Nanterre", "France", "france", 48.8924, 2.2068, 97_000),
    ("Vitry-sur-Seine", "France", "france", 48.7875, 2.3928, 95_000),
    ("Créteil", "France", "france", 48.7904, 2.4556, 92_000),
    ("Aubervilliers", "France", "france", 48.9137, 2.3835, 90_000),
    ("Colombes", "France", "france", 48.9228, 2.2540, 88_000),
    ("Aulnay-sous-Bois", "France", "france", 48.9387, 2.4906, 86_000),
    ("Asnières-sur-Seine", "France", "france", 48.9105, 2.2880, 86_000),
    ("Versailles", "France", "france", 48.8014, 2.1301, 85_000),
    ("Courbevoie", "France", "france", 48.8970, 2.2569, 82_000),
    ("Béziers", "France", "france", 43.3442, 3.2158, 80_000),
    ("Rueil-Malmaison", "France", "france", 48.8765, 2.1810, 79_000),
    ("Champigny-sur-Marne", "France", "france", 48.8172, 2.5150, 77_000),
    ("Cherbourg-en-Cotentin", "France", "france", 49.6337, -1.6221, 77_000),
    ("Antibes", "France", "france", 43.5808, 7.1239, 75_000),
    ("Cannes", "France", "france", 43.5528, 7.0174, 74_000),
    ("Mérignac", "France", "france", 44.8422, -0.6455, 70_000),
    ("Issy-les-Moulineaux", "France", "france", 48.8245, 2.2736, 69_000),
    ("Levallois-Perret", "France", "france", 48.8932, 2.2879, 68_000),
    ("Calais", "France", "france", 50.9513, 1.8587, 67_000),
    ("Vénissieux", "France", "france", 45.6976, 4.8867, 66_000),
    ("Pessac", "France", "france", 44.8067, -0.6306, 66_000),
    ("Cergy", "France", "france", 49.0364, 2.0761, 66_000),
    ("La Seyne-sur-Mer", "France", "france", 43.1000, 5.8780, 63_000),
    ("Villeneuve-d'Ascq", "France", "france", 50.6210, 3.1440, 62_000),
    ("Montauban", "France", "france", 44.0221, 1.3558, 62_000),
    ("Troyes", "France", "france", 48.2973, 4.0744, 62_000),
    ("Niort", "France", "france", 46.3237, -0.4648, 59_000),
    ("Narbonne", "France", "france", 43.1843, 3.0031, 57_000),
    ("Beauvais", "France", "france", 49.4295, 2.0807, 57_000),
    ("Fréjus", "France", "france", 43.4332, 6.7370, 55_000),
    ("La Roche-sur-Yon", "France", "france", 46.6705, -1.4260, 55_000),
    ("Cholet", "France", "france", 47.0594, -0.8798, 54_000),
    ("Saint-Quentin", "France", "france", 49.8489, 3.2876, 53_000),
    ("Cagnes-sur-Mer", "France", "france", 43.6635, 7.1480, 52_000),
    ("Vaulx-en-Velin", "France", "france", 45.7769, 4.9220, 52_000),
    ("Bourges", "France", "france", 47.0810, 2.3988, 64_000),
    ("Saint-Nazaire", "France", "france", 47.2735, -2.2138, 72_000),
    ("Fort-de-France", "France", "france", 14.6161, -61.0588, 75_000),
    ("Saint-Denis (La Réunion)", "France", "france", -20.8823, 55.4504, 155_000),
    ("Saint-Paul (La Réunion)", "France", "france", -21.0096, 55.2707, 105_000),
    ("Cayenne", "France", "france", 4.9224, -52.3135, 63_000),
    ("Mamoudzou", "France", "france", -12.7806, 45.2278, 72_000),
    ("Bremen", "Allemagne", "europe", 53.0793, 8.8017, 570_000),
    ("Dresde", "Allemagne", "europe", 51.0504, 13.7373, 560_000),
    ("Hanovre", "Allemagne", "europe", 52.3759, 9.7320, 550_000),
    ("Nuremberg", "Allemagne", "europe", 49.4521, 11.0767, 520_000),
    ("Duisbourg", "Allemagne", "europe", 51.4344, 6.7623, 500_000),
    ("Bochum", "Allemagne", "europe", 51.4818, 7.2162, 365_000),
    ("Wuppertal", "Allemagne", "europe", 51.2562, 7.1508, 355_000),
    ("Bielefeld", "Allemagne", "europe", 52.0302, 8.5325, 335_000),
    ("Bonn", "Allemagne", "europe", 50.7374, 7.0982, 335_000),
    ("Münster", "Allemagne", "europe", 51.9607, 7.6261, 320_000),
    ("Karlsruhe", "Allemagne", "europe", 49.0069, 8.4037, 310_000),
    ("Mannheim", "Allemagne", "europe", 49.4875, 8.4660, 310_000),
    ("Augsbourg", "Allemagne", "europe", 48.3705, 10.8978, 300_000),
    ("Wiesbaden", "Allemagne", "europe", 50.0782, 8.2398, 280_000),
    ("Gelsenkirchen", "Allemagne", "europe", 51.5177, 7.0857, 260_000),
    ("Aix-la-Chapelle", "Allemagne", "europe", 50.7753, 6.0839, 250_000),
    ("Mönchengladbach", "Allemagne", "europe", 51.1805, 6.4428, 260_000),
    ("Braunschweig", "Allemagne", "europe", 52.2689, 10.5268, 250_000),
    ("Chemnitz", "Allemagne", "europe", 50.8278, 12.9214, 250_000),
    ("Kiel", "Allemagne", "europe", 54.3233, 10.1228, 250_000),
    ("Fribourg-en-Brisgau", "Allemagne", "europe", 47.9990, 7.8421, 230_000),
    ("Lübeck", "Allemagne", "europe", 53.8655, 10.6866, 220_000),
    ("Mayence", "Allemagne", "europe", 49.9929, 8.2473, 220_000),
    ("Erfurt", "Allemagne", "europe", 50.9848, 11.0299, 215_000),
    ("Rostock", "Allemagne", "europe", 54.0924, 12.0991, 210_000),
    ("Murcie", "Espagne", "europe", 37.9922, -1.1307, 460_000),
    ("Palma", "Espagne", "europe", 39.5696, 2.6502, 420_000),
    ("Las Palmas de Gran Canaria", "Espagne", "europe", 28.1235, -15.4363, 380_000),
    ("Alicante", "Espagne", "europe", 38.3452, -0.4810, 350_000),
    ("Cordoue", "Espagne", "europe", 37.8882, -4.7794, 325_000),
    ("Valladolid", "Espagne", "europe", 41.6523, -4.7245, 300_000),
    ("Vigo", "Espagne", "europe", 42.2406, -8.7207, 295_000),
    ("Gijón", "Espagne", "europe", 43.5322, -5.6611, 270_000),
    ("Grenade", "Espagne", "europe", 37.1773, -3.5986, 230_000),
    ("Elche", "Espagne", "europe", 38.2699, -0.7126, 230_000),
    ("Oviedo", "Espagne", "europe", 43.3614, -5.8593, 220_000),
    ("Terrassa", "Espagne", "europe", 41.5632, 2.0089, 225_000),
    ("Sabadell", "Espagne", "europe", 41.5486, 2.1074, 220_000),
    ("Saragosse", "Espagne", "europe", 41.6488, -0.8891, 675_000),
    ("Palermo", "Italie", "europe", 38.1157, 13.3615, 630_000),
    ("Gênes", "Italie", "europe", 44.4056, 8.9463, 560_000),
    ("Bologne", "Italie", "europe", 44.4949, 11.3426, 390_000),
    ("Bari", "Italie", "europe", 41.1171, 16.8719, 315_000),
    ("Catane", "Italie", "europe", 37.5079, 15.0830, 310_000),
    ("Vérone", "Italie", "europe", 45.4384, 10.9916, 255_000),
    ("Messine", "Italie", "europe", 38.1938, 15.5540, 220_000),
    ("Padoue", "Italie", "europe", 45.4064, 11.8768, 210_000),
    ("Łódź", "Pologne", "europe", 51.7592, 19.4560, 650_000),
    ("Wrocław", "Pologne", "europe", 51.1079, 17.0385, 675_000),
    ("Poznań", "Pologne", "europe", 52.4064, 16.9252, 540_000),
    ("Lublin", "Pologne", "europe", 51.2465, 22.5684, 330_000),
    ("Bydgoszcz", "Pologne", "europe", 53.1235, 18.0084, 330_000),
    ("Szczecin", "Pologne", "europe", 53.4285, 14.5528, 390_000),
    ("Gdynia", "Pologne", "europe", 54.5189, 18.5305, 245_000),
    ("Białystok", "Pologne", "europe", 53.1325, 23.1688, 295_000),
    ("Częstochowa", "Pologne", "europe", 50.8118, 19.1203, 210_000),
    ("Brno", "Tchéquie", "europe", 49.1951, 16.6068, 380_000),
    ("Ostrava", "Tchéquie", "europe", 49.8209, 18.2625, 285_000),
    ("Cluj-Napoca", "Roumanie", "europe", 46.7712, 23.6236, 325_000),
    ("Timișoara", "Roumanie", "europe", 45.7489, 21.2087, 320_000),
    ("Iași", "Roumanie", "europe", 47.1585, 27.6014, 320_000),
    ("Constanța", "Roumanie", "europe", 44.1598, 28.6348, 300_000),
    ("Craiova", "Roumanie", "europe", 44.3302, 23.7949, 270_000),
    ("Brașov", "Roumanie", "europe", 45.6427, 25.5887, 250_000),
    ("Galati", "Roumanie", "europe", 45.4353, 28.0080, 220_000),
    ("Birmingham", "Royaume-Uni", "europe", 52.4862, -1.8904, 2_600_000),
    ("Glasgow", "Royaume-Uni", "europe", 55.8642, -4.2518, 1_700_000),
    ("Leeds", "Royaume-Uni", "europe", 53.8008, -1.5491, 1_900_000),
    ("Sheffield", "Royaume-Uni", "europe", 53.3811, -1.4701, 1_400_000),
    ("Liverpool", "Royaume-Uni", "europe", 53.4084, -2.9916, 1_500_000),
    ("Nottingham", "Royaume-Uni", "europe", 52.9548, -1.1581, 1_000_000),
    ("Leicester", "Royaume-Uni", "europe", 52.6369, -1.1398, 900_000),
    ("Coventry", "Royaume-Uni", "europe", 52.4068, -1.5197, 800_000),
    ("Cardiff", "Royaume-Uni", "europe", 51.4816, -3.1791, 1_100_000),
    ("Belfast", "Royaume-Uni", "europe", 54.5973, -5.9301, 670_000),
    ("Southampton", "Royaume-Uni", "europe", 50.9097, -1.4044, 900_000),
    ("Portsmouth", "Royaume-Uni", "europe", 50.8198, -1.0880, 850_000),
    ("Brighton", "Royaume-Uni", "europe", 50.8225, -0.1372, 630_000),
    ("Newcastle upon Tyne", "Royaume-Uni", "europe", 54.9783, -1.6178, 1_100_000),
    ("Ankara", "Turquie", "europe", 39.9334, 32.8597, 5_700_000),
    ("Izmir", "Turquie", "europe", 38.4237, 27.1428, 4_400_000),
    ("Bursa", "Turquie", "europe", 40.1885, 29.0610, 3_100_000),
    ("Gaziantep", "Turquie", "europe", 37.0662, 37.3833, 2_100_000),
    ("Kyiv", "Ukraine", "europe", 50.4501, 30.5234, 3_000_000),
    ("Kharkiv", "Ukraine", "europe", 49.9935, 36.2304, 1_400_000),
    ("Odessa", "Ukraine", "europe", 46.4825, 30.7233, 1_000_000),
    ("Dnipro", "Ukraine", "europe", 48.4647, 35.0462, 980_000),
    ("Minsk", "Biélorussie", "europe", 53.9006, 27.5590, 2_000_000),
    ("Novi Sad", "Serbie", "europe", 45.2671, 19.8335, 370_000),
    ("Plovdiv", "Bulgarie", "europe", 42.1354, 24.7453, 340_000),
    ("Varna", "Bulgarie", "europe", 43.2141, 27.9147, 330_000),
    ("Bratislava", "Slovaquie", "europe", 48.1486, 17.1077, 475_000),
    ("Košice", "Slovaquie", "europe", 48.7164, 21.2611, 230_000),
    ("Debrecen", "Hongrie", "europe", 47.5316, 21.6273, 210_000),
    ("Sarajevo", "Bosnie-Herzégovine", "europe", 43.8563, 18.4131, 420_000),
    ("Patras", "Grèce", "europe", 38.2466, 21.7346, 215_000),
    ("Graz", "Autriche", "europe", 47.0707, 15.4395, 330_000),
    ("Linz", "Autriche", "europe", 48.3069, 14.2858, 210_000),
    ("Aarhus", "Danemark", "europe", 56.1629, 10.2039, 350_000),
    ("Tampere", "Finlande", "europe", 61.4978, 23.7610, 250_000),
    ("Turku", "Finlande", "europe", 60.4518, 22.2666, 200_000),
    ("Trondheim", "Norvège", "europe", 63.4305, 10.3951, 210_000),
    ("Utrecht", "Pays-Bas", "europe", 52.0907, 5.1214, 370_000),
    ("Eindhoven", "Pays-Bas", "europe", 51.4416, 5.4697, 245_000),
    ("La Haye", "Pays-Bas", "europe", 52.0705, 4.3007, 550_000),
    ("Gand", "Belgique", "europe", 51.0543, 3.7174, 265_000),
    ("Liège", "Belgique", "europe", 50.6326, 5.5797, 200_000),
    ("Ankara", "Turquie", "europe", 39.9334, 32.8597, 5_700_000),
    ("Kazan", "Russie", "europe", 55.7961, 49.1064, 1_300_000),
    ("Nijni Novgorod", "Russie", "europe", 56.2965, 43.9361, 1_200_000),
    ("Samara", "Russie", "europe", 53.1959, 50.1002, 1_150_000),
    ("Rostov-sur-le-Don", "Russie", "europe", 47.2357, 39.7015, 1_100_000),
    ("Voronej", "Russie", "europe", 51.6755, 39.2089, 1_050_000),
    ("Oufa", "Russie", "europe", 54.7388, 55.9721, 1_100_000),
    ("Perm", "Russie", "europe", 58.0105, 56.2502, 1_050_000),
    ("Volgograd", "Russie", "europe", 48.7080, 44.5133, 1_000_000),
    ("Toronto", "Canada", "world", 43.6532, -79.3832, 6_200_000),
    ("Montréal", "Canada", "world", 45.5019, -73.5674, 4_300_000),
    ("Vancouver", "Canada", "world", 49.2827, -123.1207, 2_600_000),
    ("Guadalajara", "Mexique", "world", 20.6597, -103.3496, 5_300_000),
    ("Monterrey", "Mexique", "world", 25.6866, -100.3161, 5_300_000),
    ("Puebla", "Mexique", "world", 19.0414, -98.2063, 3_300_000),
    ("Tijuana", "Mexique", "world", 32.5149, -117.0382, 2_200_000),
    ("Houston", "États-Unis", "world", 29.7604, -95.3698, 7_500_000),
    ("Phoenix", "États-Unis", "world", 33.4484, -112.0740, 5_000_000),
    ("Philadelphie", "États-Unis", "world", 39.9526, -75.1652, 6_200_000),
    ("San Antonio", "États-Unis", "world", 29.4241, -98.4936, 2_700_000),
    ("San Diego", "États-Unis", "world", 32.7157, -117.1611, 3_300_000),
    ("Dallas", "États-Unis", "world", 32.7767, -96.7970, 7_600_000),
    ("Austin", "États-Unis", "world", 30.2672, -97.7431, 2_400_000),
    ("San José", "États-Unis", "world", 37.3382, -121.8863, 2_000_000),
    ("Jacksonville", "États-Unis", "world", 30.3322, -81.6557, 1_700_000),
    ("Columbus", "États-Unis", "world", 39.9612, -82.9988, 2_200_000),
    ("Indianapolis", "États-Unis", "world", 39.7684, -86.1581, 2_100_000),
    ("Charlotte", "États-Unis", "world", 35.2271, -80.8431, 2_800_000),
    ("Seattle", "États-Unis", "world", 47.6062, -122.3321, 4_000_000),
    ("Denver", "États-Unis", "world", 39.7392, -104.9903, 3_000_000),
    ("Nashville", "États-Unis", "world", 36.1627, -86.7816, 2_000_000),
    ("Oklahoma City", "États-Unis", "world", 35.4676, -97.5164, 1_400_000),
    ("Portland", "États-Unis", "world", 45.5152, -122.6784, 2_500_000),
    ("Las Vegas", "États-Unis", "world", 36.1699, -115.1398, 2_300_000),
    ("San Juan", "Porto Rico", "world", 18.4655, -66.1057, 2_100_000),
    ("Medellín", "Colombie", "world", 6.2476, -75.5658, 4_000_000),
    ("Cali", "Colombie", "world", 3.4516, -76.5320, 2_500_000),
    ("Barranquilla", "Colombie", "world", 10.9685, -74.7813, 2_300_000),
    ("Guayaquil", "Équateur", "world", -2.1709, -79.9224, 3_000_000),
    ("Quito", "Équateur", "world", -0.1807, -78.4678, 2_800_000),
    ("Caracas", "Venezuela", "world", 10.4806, -66.9036, 2_900_000),
    ("Maracaibo", "Venezuela", "world", 10.6427, -71.6125, 2_200_000),
    ("Belo Horizonte", "Brésil", "world", -19.9167, -43.9345, 5_700_000),
    ("Brasília", "Brésil", "world", -15.7939, -47.8828, 4_800_000),
    ("Salvador", "Brésil", "world", -12.9777, -38.5016, 3_900_000),
    ("Fortaleza", "Brésil", "world", -3.7319, -38.5267, 4_100_000),
    ("Recife", "Brésil", "world", -8.0476, -34.8770, 4_000_000),
    ("Curitiba", "Brésil", "world", -25.4284, -49.2733, 3_700_000),
    ("Porto Alegre", "Brésil", "world", -30.0346, -51.2177, 4_300_000),
    ("Manaus", "Brésil", "world", -3.1190, -60.0217, 2_300_000),
    ("Belém", "Brésil", "world", -1.4558, -48.4902, 2_500_000),
    ("Goiânia", "Brésil", "world", -16.6869, -49.2648, 2_600_000),
    ("Campinas", "Brésil", "world", -22.9056, -47.0608, 3_300_000),
    ("Santa Cruz de la Sierra", "Bolivie", "world", -17.7833, -63.1821, 2_400_000),
    ("La Paz", "Bolivie", "world", -16.4897, -68.1193, 2_000_000),
    ("Lahore", "Pakistan", "world", 31.5204, 74.3587, 13_000_000),
    ("Faisalabad", "Pakistan", "world", 31.4504, 73.1350, 3_700_000),
    ("Rawalpindi", "Pakistan", "world", 33.5651, 73.0169, 2_300_000),
    ("Chittagong", "Bangladesh", "world", 22.3569, 91.7832, 5_000_000),
    ("Khulna", "Bangladesh", "world", 22.8456, 89.5403, 1_000_000),
    ("Bengaluru", "Inde", "world", 12.9716, 77.5946, 13_600_000),
    ("Chennai", "Inde", "world", 13.0827, 80.2707, 11_800_000),
    ("Hyderabad", "Inde", "world", 17.3850, 78.4867, 10_500_000),
    ("Ahmedabad", "Inde", "world", 23.0225, 72.5714, 8_400_000),
    ("Pune", "Inde", "world", 18.5204, 73.8567, 7_400_000),
    ("Surat", "Inde", "world", 21.1702, 72.8311, 7_500_000),
    ("Jaipur", "Inde", "world", 26.9124, 75.7873, 4_100_000),
    ("Lucknow", "Inde", "world", 26.8467, 80.9462, 3_800_000),
    ("Kanpur", "Inde", "world", 26.4499, 80.3319, 3_200_000),
    ("Nagpur", "Inde", "world", 21.1458, 79.0882, 2_900_000),
    ("Indore", "Inde", "world", 22.7196, 75.8577, 3_000_000),
    ("Bhopal", "Inde", "world", 23.2599, 77.4126, 2_500_000),
    ("Patna", "Inde", "world", 25.5941, 85.1376, 2_600_000),
    ("Agra", "Inde", "world", 27.1767, 78.0081, 1_700_000),
    ("Vadodara", "Inde", "world", 22.3072, 73.1812, 2_200_000),
    ("Coimbatore", "Inde", "world", 11.0168, 76.9558, 2_500_000),
    ("Kochi", "Inde", "world", 9.9312, 76.2673, 2_100_000),
    ("Guwahati", "Inde", "world", 26.1445, 91.7362, 1_200_000),
    ("Surabaya", "Indonésie", "world", -7.2575, 112.7521, 6_500_000),
    ("Bandung", "Indonésie", "world", -6.9175, 107.6191, 2_700_000),
    ("Medan", "Indonésie", "world", 3.5952, 98.6722, 2_500_000),
    ("Semarang", "Indonésie", "world", -6.9667, 110.4167, 1_700_000),
    ("Palembang", "Indonésie", "world", -2.9761, 104.7754, 1_700_000),
    ("Makassar", "Indonésie", "world", -5.1477, 119.4327, 1_600_000),
    ("Hô Chi Minh-Ville", "Vietnam", "world", 10.8231, 106.6297, 9_300_000),
    ("Da Nang", "Vietnam", "world", 16.0544, 108.2022, 1_200_000),
    ("Yangon", "Myanmar", "world", 16.8409, 96.1735, 5_500_000),
    ("Mandalay", "Myanmar", "world", 21.9588, 96.0891, 1_300_000),
    ("Phnom Penh", "Cambodge", "world", 11.5564, 104.9282, 2_300_000),
    ("Kuala Lumpur", "Malaisie", "world", 3.1390, 101.6869, 8_400_000),
    ("George Town", "Malaisie", "world", 5.4141, 100.3288, 2_500_000),
    ("Davao", "Philippines", "world", 7.1907, 125.4553, 1_800_000),
    ("Cebu", "Philippines", "world", 10.3157, 123.8854, 2_900_000),
    ("Sapporo", "Japon", "world", 43.0618, 141.3545, 2_600_000),
    ("Yokohama", "Japon", "world", 35.4437, 139.6380, 3_800_000),
    ("Kobe", "Japon", "world", 34.6901, 135.1956, 1_500_000),
    ("Kyoto", "Japon", "world", 35.0116, 135.7681, 1_500_000),
    ("Hiroshima", "Japon", "world", 34.3853, 132.4553, 1_200_000),
    ("Sendai", "Japon", "world", 38.2682, 140.8694, 1_100_000),
    ("Kitakyushu", "Japon", "world", 33.8834, 130.8752, 1_000_000),
    ("Incheon", "Corée du Sud", "world", 37.4563, 126.7052, 3_000_000),
    ("Daegu", "Corée du Sud", "world", 35.8714, 128.6014, 2_400_000),
    ("Daejeon", "Corée du Sud", "world", 36.3504, 127.3845, 1_500_000),
    ("Gwangju", "Corée du Sud", "world", 35.1595, 126.8526, 1_500_000),
    ("Tianjin", "Chine", "world", 39.3434, 117.3616, 13_900_000),
    ("Guangzhou", "Chine", "world", 23.1291, 113.2644, 18_700_000),
    ("Shenzhen", "Chine", "world", 22.5431, 114.0579, 17_600_000),
    ("Wuhan", "Chine", "world", 30.5928, 114.3055, 12_300_000),
    ("Nanjing", "Chine", "world", 32.0603, 118.7969, 9_500_000),
    ("Hangzhou", "Chine", "world", 30.2741, 120.1551, 12_200_000),
    ("Harbin", "Chine", "world", 45.8038, 126.5350, 10_000_000),
    ("Shenyang", "Chine", "world", 41.8057, 123.4315, 9_000_000),
    ("Changsha", "Chine", "world", 28.2282, 112.9388, 10_000_000),
    ("Zhengzhou", "Chine", "world", 34.7466, 113.6253, 10_000_000),
    ("Jinan", "Chine", "world", 36.6512, 117.1201, 9_200_000),
    ("Qingdao", "Chine", "world", 36.0671, 120.3826, 10_000_000),
    ("Dalian", "Chine", "world", 38.9140, 121.6147, 7_500_000),
    ("Kunming", "Chine", "world", 25.0389, 102.7183, 8_600_000),
    ("Fuzhou", "Chine", "world", 26.0745, 119.2965, 8_300_000),
    ("Xiamen", "Chine", "world", 24.4798, 118.0894, 5_300_000),
    ("Hefei", "Chine", "world", 31.8206, 117.2272, 9_500_000),
    ("Ürümqi", "Chine", "world", 43.8256, 87.6168, 4_000_000),
    ("Nanning", "Chine", "world", 22.8170, 108.3665, 8_800_000),
    ("Shijiazhuang", "Chine", "world", 38.0428, 114.5149, 11_000_000),
    ("Taiyuan", "Chine", "world", 37.8706, 112.5489, 5_400_000),
    ("Lanzhou", "Chine", "world", 36.0611, 103.8343, 4_400_000),
    ("Nanchang", "Chine", "world", 28.6820, 115.8579, 6_400_000),
    ("Guiyang", "Chine", "world", 26.6470, 106.6302, 6_200_000),
    ("Jilin", "Chine", "world", 43.8378, 126.5496, 3_600_000),
    ("Ulaanbaatar", "Mongolie", "world", 47.9184, 106.9177, 1_600_000),
    ("Téhéran", "Iran", "world", 35.6892, 51.3890, 9_500_000),
    ("Mashhad", "Iran", "world", 36.2605, 59.6168, 3_400_000),
    ("Ispahan", "Iran", "world", 32.6546, 51.6680, 2_300_000),
    ("Tabriz", "Iran", "world", 38.0962, 46.2738, 1_700_000),
    ("Riyad", "Arabie saoudite", "world", 24.7136, 46.6753, 7_700_000),
    ("Djeddah", "Arabie saoudite", "world", 21.4858, 39.1925, 4_700_000),
    ("La Mecque", "Arabie saoudite", "world", 21.3891, 39.8579, 2_400_000),
    ("Bagdad", "Irak", "world", 33.3152, 44.3661, 8_100_000),
    ("Bassorah", "Irak", "world", 30.5085, 47.7804, 2_600_000),
    ("Amman", "Jordanie", "world", 31.9454, 35.9284, 4_000_000),
    ("Damas", "Syrie", "world", 33.5138, 36.2765, 2_500_000),
    ("Sanaa", "Yémen", "world", 15.3694, 44.1910, 3_000_000),
    ("Lagos", "Nigeria", "world", 6.5244, 3.3792, 15_400_000),
    ("Kano", "Nigeria", "world", 12.0022, 8.5920, 4_000_000),
    ("Ibadan", "Nigeria", "world", 7.3775, 3.9470, 3_600_000),
    ("Accra", "Ghana", "world", 5.6037, -0.1870, 5_500_000),
    ("Kumasi", "Ghana", "world", 6.6885, -1.6244, 3_600_000),
    ("Abidjan", "Côte d'Ivoire", "world", 5.3599, -4.0083, 6_300_000),
    ("Dakar", "Sénégal", "world", 14.7167, -17.4677, 3_900_000),
    ("Kinshasa", "République démocratique du Congo", "world", -4.4419, 15.2663, 17_000_000),
    ("Luanda", "Angola", "world", -8.8390, 13.2894, 9_000_000),
    ("Dar es Salaam", "Tanzanie", "world", -6.7924, 39.2083, 7_400_000),
    ("Addis-Abeba", "Éthiopie", "world", 8.9806, 38.7578, 5_700_000),
    ("Alexandrie", "Égypte", "world", 31.2001, 29.9187, 5_500_000),
    ("Casablanca", "Maroc", "world", 33.5731, -7.5898, 4_300_000),
    ("Le Cap", "Afrique du Sud", "world", -33.9249, 18.4241, 4_800_000),
    ("Durban", "Afrique du Sud", "world", -29.8587, 31.0218, 3_900_000),
    ("Pretoria", "Afrique du Sud", "world", -25.7479, 28.2293, 2_900_000),
    ("Khartoum", "Soudan", "world", 15.5007, 32.5599, 5_500_000),
    ("Kampala", "Ouganda", "world", 0.3476, 32.5825, 3_700_000),
    ("Kigali", "Rwanda", "world", -1.9441, 30.0619, 1_700_000),
    ("Tunis", "Tunisie", "world", 36.8065, 10.1815, 2_700_000),
    ("Oran", "Algérie", "world", 35.6971, -0.6308, 1_600_000),
    ("Constantine", "Algérie", "world", 36.3650, 6.6147, 1_000_000),
    ("Antananarivo", "Madagascar", "world", -18.8792, 47.5079, 3_300_000),
    ("New Taipei", "Taïwan", "world", 25.0169, 121.4628, 4_000_000),
    ("Taichung", "Taïwan", "world", 24.1477, 120.6736, 2_800_000),
    ("Kaohsiung", "Taïwan", "world", 22.6273, 120.3014, 2_700_000),
    ("Medan", "Indonésie", "world", 3.5952, 98.6722, 2_500_000),
    ("Kathmandu", "Népal", "world", 27.7172, 85.3240, 1_700_000),
)


def validate_region(region: str) -> str:
    normalized = region.strip().lower()
    if normalized not in GEOGUESSR_REGIONS:
        raise ValueError("Choisissez une zone valide : France, Europe ou Monde.")
    return normalized


def _city_pool(region: str) -> List[tuple[str, str, str, float, float]]:
    region = validate_region(region)
    selected = [
        city for city in CITY_LOCATIONS
        if region == "world"
        or (region == "france" and city[2] == "france")
        or (region == "europe" and city[2] in {"france", "europe"})
    ]
    minimum_population = {"france": 50_000, "europe": 200_000, "world": 1_000_000}[region]
    selected.extend(
        (city[0], city[1], city[2], city[3], city[4])
        for city in CITY_ADDITIONS
        if city[5] >= minimum_population
        and (
            region == "world"
            or (region == "france" and city[2] == "france")
            or (region == "europe" and city[2] == "europe")
            or (
                region == "europe"
                and city[2] == "france"
                and 41 <= city[3] <= 52
                and -6 <= city[4] <= 10
            )
        )
    )
    if not selected:
        raise ValueError("Aucune ville n'est disponible pour cette zone.")
    unique: Dict[tuple[str, str], tuple[str, str, str, float, float]] = {}
    for city in selected:
        unique.setdefault((city[0], city[1]), city)
    return list(unique.values())


def _sample_city_round(
    region: str,
    round_count: int,
    excluded_cities: Optional[Set[tuple[str, str]]] = None,
) -> List[tuple[str, str, str, float, float]]:
    excluded_cities = excluded_cities or set()
    by_country: Dict[str, List[tuple[str, str, str, float, float]]] = {}
    for city in _city_pool(region):
        if (city[0], city[1]) not in excluded_cities:
            by_country.setdefault(city[1], []).append(city)

    selected: List[tuple[str, str, str, float, float]] = []
    selected_countries: Set[str] = set()
    while len(selected) < min(round_count, sum(map(len, by_country.values()))):
        available_countries = [
            country for country, cities in by_country.items()
            if cities and country not in selected_countries
        ]
        if not available_countries:
            available_countries = [
                country for country, cities in by_country.items() if cities
            ]
        country = random.choice(available_countries)
        city = random.choice(by_country[country])
        by_country[country].remove(city)
        selected.append(city)
        selected_countries.add(country)
    return selected


def _diverse_city_order(
    region: str,
    used_countries: Optional[Set[str]] = None,
    used_cities: Optional[Set[tuple[str, str]]] = None,
) -> List[tuple[str, str, str, float, float]]:
    used_countries = used_countries or set()
    used_cities = used_cities or set()
    by_country: Dict[str, List[tuple[str, str, str, float, float]]] = {}
    for city in _city_pool(region):
        if (city[0], city[1]) not in used_cities:
            by_country.setdefault(city[1], []).append(city)

    for cities in by_country.values():
        random.shuffle(cities)
    representatives = {
        country: cities[-1] for country, cities in by_country.items()
    }
    countries = list(by_country)
    random.shuffle(countries)
    ordered_countries: List[str] = []
    for already_used in (False, True):
        candidates = [
            country for country in countries
            if (country in used_countries) is already_used
        ]
        while candidates:
            if not ordered_countries:
                selected_country = random.choice(candidates)
            else:
                distances = {
                    country: min(
                        distance_km(
                            representatives[country][3],
                            representatives[country][4],
                            representatives[previous][3],
                            representatives[previous][4],
                        )
                        for previous in ordered_countries
                    )
                    for country in candidates
                }
                farthest_distance = max(distances.values())
                farthest_countries = [
                    country for country, distance in distances.items()
                    if distance == farthest_distance
                ]
                selected_country = random.choice(farthest_countries)
            ordered_countries.append(selected_country)
            candidates.remove(selected_country)

    ordered = []
    while any(by_country.values()):
        for country in ordered_countries:
            if by_country[country]:
                ordered.append(by_country[country].pop())
    return ordered


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lat1, lat2 = math.radians(lat_a), math.radians(lat_b)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(lon_b - lon_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def score_distance_km(distance: float) -> int:
    return max(0, min(MAX_SCORE_PER_ROUND, round(MAX_SCORE_PER_ROUND * math.exp(-distance / 2_000))))


def _choose_city(region: str, previous: set[str]) -> tuple[str, str, str, float, float]:
    pool = _city_pool(region)
    choices = [city for city in pool if city[0] not in previous] or pool
    return random.choice(choices)


def _public_city(city: tuple[str, str, str, float, float]) -> Dict[str, Any]:
    return {
        "city": city[0],
        "country": city[1],
        "latitude": city[3],
        "longitude": city[4],
    }


def _score_guess(city: tuple[str, str, str, float, float], latitude: float, longitude: float) -> Dict[str, Any]:
    distance = distance_km(latitude, longitude, city[3], city[4])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "distance_km": round(distance, 1),
        "score": score_distance_km(distance),
    }


@dataclass
class GeoGuessrGame:
    game_id: str
    player_id: str
    player_name: str
    region: str
    cities: List[tuple[str, str, str, float, float]]
    variant: str = "cities"
    image_ids: List[str] = field(default_factory=list)
    panorama_provider: Optional[str] = None
    google_viewed_rounds: Set[Tuple[str, int]] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    total_score: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "playing"
    awaiting_next_round: bool = False

    @property
    def target(self) -> tuple[str, str, str, float, float]:
        return self.cities[min(self.round_index, len(self.cities) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        last_result = self.results[-1] if self.results else None
        prompt = (
            self.cities[self.round_index]
            if self.status == "playing" and not self.awaiting_next_round
            else None
        )
        return {
            "game_id": self.game_id,
            "status": self.status,
            "mode": "solo",
            "variant": self.variant,
            "panorama_provider": self.panorama_provider,
            "region": self.region,
            "round_number": min(self.round_index + 1, ROUND_COUNT),
            "round_count": ROUND_COUNT,
            "total_score": self.total_score,
            "max_total_score": ROUND_COUNT * MAX_SCORE_PER_ROUND,
            "round_results": self.results,
            "last_result": last_result,
            "awaiting_next_round": self.awaiting_next_round,
            "prompt": {"city": prompt[0], "country": prompt[1]} if prompt else None,
            "image_id": (
                self.image_ids[min(self.round_index, len(self.image_ids) - 1)]
                if self.variant == "panorama" and self.image_ids
                else None
            ),
            "target": _public_city(self.cities[-1]) if self.status == "finished" else None,
        }


@dataclass
class GeoGuessrRoomPlayer:
    player_id: str
    name: str
    total_score: int = 0
    guess: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    connected: bool = True
    is_spectator: bool = False
    ready: bool = False

    def public_state(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "total_score": self.total_score,
            "is_spectator": self.is_spectator,
            "ready": self.ready,
            "submitted": self.guess is not None,
            "guess": (
                {"latitude": self.guess["latitude"], "longitude": self.guess["longitude"]}
                if self.guess else None
            ),
            "round_results": self.results,
            "connected": self.connected,
        }


@dataclass
class GeoGuessrRoom:
    room_id: str
    host_player_id: str
    region: str
    cities: List[tuple[str, str, str, float, float]]
    variant: str = "cities"
    image_ids: List[str] = field(default_factory=list)
    panorama_provider: Optional[str] = None
    google_viewed_rounds: Set[Tuple[str, int]] = field(default_factory=set)
    players: Dict[str, GeoGuessrRoomPlayer] = field(default_factory=dict)
    status: str = "lobby"
    round_index: int = 0
    last_round: Optional[Dict[str, Any]] = None
    awaiting_next_round: bool = False
    round_deadline: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    stats_recorded: bool = False
    match_number: int = 1
    round_count: int = ROUND_COUNT

    @property
    def target(self) -> tuple[str, str, str, float, float]:
        return self.cities[min(self.round_index, len(self.cities) - 1)]

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        prompt = (
            self.cities[self.round_index]
            if self.status == "playing" and self.variant == "cities"
            else None
        )
        return {
            "room_id": self.room_id,
            "match_number": self.match_number,
            "host_player_id": self.host_player_id,
            "status": self.status,
            "variant": self.variant,
            "panorama_provider": self.panorama_provider,
            "region": self.region,
            "round_number": min(self.round_index + 1, self.round_count),
            "round_count": self.round_count,
            "round_deadline": self.round_deadline,
            "round_time_limit_seconds": ROOM_ROUND_TIME_LIMIT_SECONDS,
            "max_players": MAX_PLAYERS,
            "awaiting_next_round": self.awaiting_next_round,
            "ready_count": sum(
                item.ready for item in self.players.values() if not item.is_spectator
            ),
            "all_ready": (
                sum(not item.is_spectator for item in self.players.values()) >= 2
                and all(
                    item.ready for item in self.players.values() if not item.is_spectator
                )
            ),
            "can_start": (
                self.status == "lobby"
                and sum(not item.is_spectator for item in self.players.values()) >= 2
                and all(
                    item.ready for item in self.players.values() if not item.is_spectator
                )
            ),
            "player_count": sum(not item.is_spectator for item in self.players.values()),
            "spectator_count": sum(item.is_spectator for item in self.players.values()),
            "players": [item.public_state() for item in self.players.values()],
            "player": player.public_state(),
            "last_round": self.last_round,
            "prompt": {"city": prompt[0], "country": prompt[1]} if prompt else None,
            "image_id": (
                self.image_ids[min(self.round_index, len(self.image_ids) - 1)]
                if self.variant == "panorama" and self.image_ids and self.status != "lobby"
                else None
            ),
            "target": self.last_round["target"] if self.status == "finished" and self.last_round else None,
        }


class GeoGuessrManager:
    def __init__(
        self,
        mapillary_access_token: Optional[str] = None,
        google_maps_server_api_key: Optional[str] = None,
        google_maps_browser_api_key: Optional[str] = None,
        google_usage_reader: Callable[[], int] = get_geoguessr_google_usage,
        google_usage_reserver: Callable[[int, int], bool] = reserve_geoguessr_google_usage,
    ) -> None:
        self.solo_games: Dict[str, GeoGuessrGame] = {}
        self.rooms: Dict[str, GeoGuessrRoom] = {}
        self.solo_city_bags: Dict[
            Tuple[str, str], List[tuple[str, str, str, float, float]]
        ] = {}
        self.last_solo_city_keys: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
        self.mapillary_access_token = (
            mapillary_access_token or os.environ.get("MAPILLARY_ACCESS_TOKEN", "")
        ).strip()
        self.google_maps_server_api_key = (
            google_maps_server_api_key or os.environ.get("GOOGLE_MAPS_SERVER_API_KEY", "")
        ).strip()
        self.google_maps_browser_api_key = (
            google_maps_browser_api_key or os.environ.get("GOOGLE_MAPS_BROWSER_API_KEY", "")
        ).strip()
        self.google_usage_reader = google_usage_reader
        self.google_usage_reserver = google_usage_reserver
        self.photo_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.used_photo_image_ids: Dict[str, Set[str]] = {}
        self.used_photo_sequence_ids: Dict[str, Set[str]] = {}
        self.lock = threading.RLock()

    def google_usage(self) -> int:
        return self.google_usage_reader()

    def _get_google_targets(
        self, region: str, round_count: int = ROUND_COUNT,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str]]:
        if not self.google_maps_server_api_key:
            raise ValueError("La clé Google Maps n’est pas configurée.")

        targets: List[tuple[str, str, str, float, float]] = []
        image_ids: List[str] = []
        seen_panorama_ids: Set[str] = set()
        candidates = _diverse_city_order(region)
        attempts = 0
        while (
            len(targets) < round_count
            and attempts < min(round_count * 8, len(candidates))
        ):
            city = candidates[attempts]
            attempts += 1
            latitude = city[3] + random.uniform(-0.025, 0.025)
            longitude = city[4] + random.uniform(-0.025, 0.025)
            try:
                response = requests.get(
                    GOOGLE_STREETVIEW_METADATA_URL,
                    params={
                        "location": f"{latitude:.6f},{longitude:.6f}",
                        "radius": 1_000,
                        "source": "outdoor",
                        "key": self.google_maps_server_api_key,
                    },
                    timeout=(3.05, 8),
                )
                response.raise_for_status()
                metadata = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise ValueError(
                    "Impossible de joindre Google Street View. Vérifiez la clé API et la facturation."
                ) from exc

            if metadata.get("status") == "ZERO_RESULTS":
                continue
            if metadata.get("status") != "OK":
                if metadata.get("status") == "REQUEST_DENIED":
                    raise ValueError(
                        "Google Street View a refusé la clé serveur. Vérifiez que "
                        "Street View Static API est activée, que la facturation est "
                        "active et que les restrictions autorisent les requêtes du serveur."
                    )
                raise ValueError(
                    "Google Street View n’a pas fourni de photo "
                    f"({metadata.get('status', 'réponse invalide')})."
                )

            panorama_id = str(metadata.get("pano_id") or "")
            location = metadata.get("location") or {}
            if (
                not panorama_id
                or panorama_id in seen_panorama_ids
                or "lat" not in location
                or "lng" not in location
            ):
                continue
            targets.append((
                "Lieu de la photo",
                "",
                region,
                float(location["lat"]),
                float(location["lng"]),
            ))
            image_ids.append(panorama_id)
            seen_panorama_ids.add(panorama_id)

        if len(targets) < round_count:
            raise ValueError("Google Street View n’a pas trouvé assez de photos dans cette zone.")
        return targets, image_ids

    def _get_panorama_targets(
        self,
        region: str,
        *,
        reserve_google_views: bool,
        google_viewer_count: int = 1,
        round_count: int = ROUND_COUNT,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str], str]:
        google_error: Optional[Exception] = None
        if self.google_maps_server_api_key and self.google_maps_browser_api_key:
            try:
                reserved_usage = round_count * google_viewer_count
                if (
                    self.google_usage() + reserved_usage
                    <= GOOGLE_STREETVIEW_MONTHLY_LIMIT
                ):
                    targets, image_ids = self._get_google_targets(region, round_count)
                    if not reserve_google_views or self.google_usage_reserver(
                        reserved_usage, GOOGLE_STREETVIEW_MONTHLY_LIMIT
                    ):
                        return targets, image_ids, "google"
            except Exception as exc:
                google_error = exc
                logger.warning(
                    "Google Street View indisponible, repli sur Mapillary : %s",
                    exc,
                )

        if not self.mapillary_access_token and isinstance(google_error, ValueError):
            raise google_error
        targets, image_ids = self._get_mapillary_targets(region, round_count)
        return targets, image_ids, "mapillary"

    def _get_mapillary_targets(
        self, region: str, round_count: int = ROUND_COUNT,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str]]:
        if not self.mapillary_access_token:
            raise ValueError(
                "Aucun fournisseur photo n’est disponible : configurez "
                "GOOGLE_MAPS_BROWSER_API_KEY et GOOGLE_MAPS_SERVER_API_KEY, "
                "ou MAPILLARY_ACCESS_TOKEN sur le serveur."
            )

        cached = self.photo_cache.setdefault(region, [])
        selected: List[Dict[str, Any]] = []
        used_image_ids = self.used_photo_image_ids.setdefault(region, set())
        used_sequence_ids = self.used_photo_sequence_ids.setdefault(region, set())
        seen_sequences = set(used_sequence_ids)
        cached_by_city: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for image in cached:
            city_name = image.get("source_city_name")
            country = image.get("source_country")
            if not city_name or not country or not image.get("sequence_id"):
                continue
            city_key = (city_name, country)
            cached_by_city.setdefault(city_key, []).append(image)
        used_cities: set[tuple[str, str]] = set()
        for city in _diverse_city_order(region):
            city_key = (city[0], city[1])
            cached_images = [
                image for image in cached_by_city.get(city_key, [])
                if image["image_id"] not in used_image_ids
                and image["sequence_id"] not in seen_sequences
            ]
            if not cached_images:
                continue
            image = random.choice(cached_images)
            selected.append(image)
            seen_sequences.add(image["sequence_id"])
            used_cities.add(city_key)
            if len(selected) == round_count:
                break

        candidates = _diverse_city_order(
            region,
            used_countries={image["source_country"] for image in selected},
            used_cities=used_cities,
        )
        attempts = 0
        while (
            len(selected) < round_count
            and attempts < min(round_count * 8, len(candidates))
        ):
            city = candidates[attempts]
            attempts += 1
            latitude = city[3] + random.uniform(-0.025, 0.025)
            longitude = city[4] + random.uniform(-0.025, 0.025)
            delta = 0.0045
            bbox = (
                max(-180, longitude - delta),
                max(-90, latitude - delta),
                min(180, longitude + delta),
                min(90, latitude + delta),
            )
            try:
                response = requests.get(
                    MAPILLARY_API_URL,
                    params={
                        "bbox": ",".join(f"{coordinate:.6f}" for coordinate in bbox),
                        "fields": "id,geometry,sequence_id,is_pano",
                        "limit": 100,
                    },
                    headers={"Authorization": f"OAuth {self.mapillary_access_token}"},
                    timeout=(3.05, 8),
                )
            except requests.RequestException as exc:
                raise ValueError("Impossible de joindre Mapillary. Réessayez dans un instant.") from exc
            if response.status_code == 429:
                raise ValueError("Mapillary limite temporairement les requêtes. Réessayez dans un instant.")
            if not response.ok:
                raise ValueError(
                    f"Mapillary a refusé la requête (HTTP {response.status_code}). Vérifiez le jeton configuré."
                )
            try:
                images = response.json().get("data", [])
            except ValueError as exc:
                raise ValueError("Mapillary a renvoyé une réponse invalide.") from exc
            for image in images:
                sequence_id = image.get("sequence_id")
                coordinates = (image.get("geometry") or {}).get("coordinates")
                if (
                    not sequence_id
                    or not isinstance(coordinates, list)
                    or len(coordinates) < 2
                    or sequence_id in seen_sequences
                ):
                    continue
                image_id = str(image.get("id", ""))
                if not image_id or image_id in used_image_ids:
                    continue
                target = {
                    "image_id": image_id,
                    "sequence_id": str(sequence_id),
                    "latitude": float(coordinates[1]),
                    "longitude": float(coordinates[0]),
                    "source_city_name": city[0],
                    "source_country": city[1],
                }
                if not any(item["image_id"] == image_id for item in cached):
                    cached.append(target)
                selected.append(target)
                seen_sequences.add(str(sequence_id))
                used_cities.add((city[0], city[1]))
                break

        if len(selected) < round_count:
            raise ValueError(
                "Mapillary n’a pas trouvé assez de séquences navigables dans cette zone. Réessayez."
            )

        used_image_ids.update(item["image_id"] for item in selected)
        used_sequence_ids.update(item["sequence_id"] for item in selected)
        targets = [
            ("Lieu de la photo", "", region, item["latitude"], item["longitude"])
            for item in selected
        ]
        return targets, [item["image_id"] for item in selected]

    def create_solo(
        self, player_id: str, player_name: str, region: str = "world", variant: str = "cities",
    ) -> GeoGuessrGame:
        region = validate_region(region)
        if variant not in GEOGUESSR_VARIANTS:
            raise ValueError("Choisissez un mode GeoGuessr valide.")
        image_ids: List[str] = []
        panorama_provider: Optional[str] = None
        if variant == "panorama":
            cities, image_ids, panorama_provider = self._get_panorama_targets(
                region,
                reserve_google_views=True,
            )
        else:
            with self.lock:
                history_key = (player_id, region)
                city_bag = self.solo_city_bags.setdefault(history_key, [])
                if len(city_bag) < ROUND_COUNT:
                    excluded_cities = self.last_solo_city_keys.get(history_key, set())
                    excluded_cities = excluded_cities | {
                        (city[0], city[1]) for city in city_bag
                    }
                    next_cities = _diverse_city_order(
                        region,
                        used_cities=excluded_cities,
                    )
                    if len(city_bag) + len(next_cities) < ROUND_COUNT:
                        next_cities = _diverse_city_order(
                            region,
                            used_cities={(city[0], city[1]) for city in city_bag},
                        )
                    city_bag.extend(next_cities)
                cities = city_bag[:ROUND_COUNT]
                del city_bag[:ROUND_COUNT]
                self.last_solo_city_keys[history_key] = {
                    (city[0], city[1]) for city in cities
                }
        with self.lock:
            game = GeoGuessrGame(
                str(uuid.uuid4()), player_id, player_name.strip()[:24], region,
                cities, variant, image_ids, panorama_provider,
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> GeoGuessrGame:
        with self.lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Partie introuvable.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, latitude: float, longitude: float,
    ) -> tuple[GeoGuessrGame, Dict[str, Any]]:
        with self.lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est déjà terminée.")
            if game.awaiting_next_round:
                raise ValueError("Consultez d'abord le résultat de la manche précédente.")
            result = _score_guess(game.target, latitude, longitude)
            result["guess_latitude"] = latitude
            result["guess_longitude"] = longitude
            result.update(_public_city(game.target))
            result["round_number"] = game.round_index + 1
            game.results.append(result)
            game.total_score += result["score"]
            if game.round_index + 1 == ROUND_COUNT:
                game.status = "finished"
            else:
                game.awaiting_next_round = True
            return game, result

    def next_solo_round(self, game_id: str, player_id: str) -> GeoGuessrGame:
        with self.lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est déjà terminée.")
            if not game.awaiting_next_round:
                raise ValueError("Aucun résultat n'attend votre confirmation.")
            game.round_index += 1
            game.awaiting_next_round = False
            return game

    def create_room(
        self,
        player_id: str,
        player_name: str,
        region: str = "world",
        variant: str = "cities",
        round_count: int = ROUND_COUNT,
    ) -> GeoGuessrRoom:
        region = validate_region(region)
        if variant not in GEOGUESSR_VARIANTS:
            raise ValueError("Choisissez un mode GeoGuessr valide.")
        if type(round_count) is not int or not 1 <= round_count <= 20:
            raise ValueError("Le nombre de manches doit être compris entre 1 et 20.")
        image_ids: List[str] = []
        panorama_provider: Optional[str] = None
        if variant == "panorama":
            cities, image_ids, panorama_provider = self._get_panorama_targets(
                region,
                reserve_google_views=False,
                round_count=round_count,
            )
        else:
            cities = _sample_city_round(region, round_count)
        with self.lock:
            room_id = uuid.uuid4().hex[:6].upper()
            room = GeoGuessrRoom(
                room_id,
                player_id,
                region,
                cities,
                variant,
                image_ids,
                panorama_provider,
                round_count=round_count,
            )
            room.players[player_id] = GeoGuessrRoomPlayer(player_id, player_name.strip()[:24])
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> GeoGuessrRoom:
        with self.lock:
            room = self.rooms.get(room_id.strip().upper())
            if not room:
                raise KeyError("Salon introuvable.")
            if player_id in room.players:
                room.players[player_id].connected = True
                return room
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError("Ce salon est complet.")
            if room.status == "lobby":
                for player in room.players.values():
                    player.ready = False
            room.players[player_id] = GeoGuessrRoomPlayer(
                player_id,
                player_name.strip()[:24],
                is_spectator=room.status != "lobby",
            )
            return room

    def start_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        with self.lock:
            room = self._get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if sum(not player.is_spectator for player in room.players.values()) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            if not all(
                player.ready for player in room.players.values() if not player.is_spectator
            ):
                raise ValueError("Tous les joueurs doivent confirmer qu'ils sont prêts.")
            room.cities, room.image_ids, room.panorama_provider = (
                self._prepare_room_panorama_views(
                    room.region,
                    room.players,
                    room.cities,
                    room.image_ids,
                    room.panorama_provider,
                    room.round_count,
                )
            )
            room.status = "playing"
            room.round_deadline = None
            room.started_at = time.time()
            for player in room.players.values():
                player.ready = False
            return room

    def restart_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        with self.lock:
            room = self._get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut relancer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être relancée.")

            if room.variant == "panorama":
                cities, image_ids, provider = self._get_panorama_targets(
                    room.region,
                    reserve_google_views=False,
                    round_count=room.round_count,
                )
            else:
                pool = _city_pool(room.region)
                cities = random.sample(pool, k=room.round_count)
                image_ids, provider = [], None
            cities, image_ids, provider = self._prepare_room_panorama_views(
                room.region,
                room.players,
                cities,
                image_ids,
                provider,
                room.round_count,
            )

            room.cities = cities
            room.image_ids = image_ids
            room.panorama_provider = provider
            room.google_viewed_rounds.clear()
            room.round_index = 0
            room.last_round = None
            room.awaiting_next_round = False
            room.round_deadline = None
            room.status = "playing"
            room.started_at = time.time()
            room.stats_recorded = False
            room.match_number += 1
            for player in room.players.values():
                player.total_score = 0
                player.guess = None
                player.ready = False
                player.results.clear()
                player.is_spectator = False
            return room

    def _prepare_room_panorama_views(
        self,
        region: str,
        players: Dict[str, GeoGuessrRoomPlayer],
        cities: List[tuple[str, str, str, float, float]],
        image_ids: List[str],
        provider: Optional[str],
        round_count: int,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str], Optional[str]]:
        if provider != "google":
            return cities, image_ids, provider
        required_views = round_count * len(players)
        try:
            reserved = self.google_usage_reserver(
                required_views,
                GOOGLE_STREETVIEW_MONTHLY_LIMIT,
            )
        except Exception as exc:
            logger.warning(
                "Réservation Google impossible, repli sur Mapillary : %s",
                exc,
            )
            reserved = False
        if not reserved:
            cities, image_ids = self._get_mapillary_targets(region, round_count)
            provider = "mapillary"
        return cities, image_ids, provider

    def authorize_google_view(
        self,
        player_id: str,
        *,
        game_id: Optional[str] = None,
        room_id: Optional[str] = None,
        navigation: bool = False,
    ) -> bool:
        with self.lock:
            if game_id:
                game = self.get_solo(game_id, player_id)
                if (
                    game.status != "playing"
                    or game.variant != "panorama"
                    or game.panorama_provider != "google"
                ):
                    raise ValueError("Cette partie n’utilise pas Google Street View.")
                viewed_rounds = game.google_viewed_rounds
                round_index = game.round_index
            elif room_id:
                room = self._get_room(room_id, player_id)
                if (
                    room.status != "playing"
                    or room.variant != "panorama"
                    or room.panorama_provider != "google"
                ):
                    raise ValueError("Ce salon n’utilise pas Google Street View.")
                viewed_rounds = room.google_viewed_rounds
                round_index = room.round_index
            else:
                raise ValueError("Une partie solo ou un salon est requis.")

            round_key = (player_id, round_index)
            if navigation or round_key in viewed_rounds:
                return self.google_usage_reserver(
                    1,
                    GOOGLE_STREETVIEW_MONTHLY_LIMIT,
                )
            viewed_rounds.add(round_key)
            return True

    def guess_room(
        self, room_id: str, player_id: str, latitude: float, longitude: float,
    ) -> tuple[GeoGuessrRoom, Optional[Dict[str, Any]]]:
        with self.lock:
            room = self._get_room(room_id, player_id)
            player = room.players[player_id]
            if room.status == "playing" and player.is_spectator:
                raise ValueError("Vous êtes spectateur et rejoindrez la prochaine manche.")
            if (
                room.round_deadline is not None
                and time.time() >= room.round_deadline
            ):
                self._finish_room_round(room)
                return room, room.last_round
            if room.awaiting_next_round:
                raise ValueError("Confirmez d'abord la manche précédente.")
            if room.status != "playing":
                raise ValueError("La partie n'accepte pas de réponse pour le moment.")
            if player.guess is not None:
                raise ValueError("Votre position est déjà validée pour cette manche.")
            player.guess = _score_guess(room.target, latitude, longitude)
            if room.round_deadline is None:
                room.round_deadline = time.time() + ROOM_ROUND_TIME_LIMIT_SECONDS
            active_players = [
                item for item in room.players.values() if not item.is_spectator
            ]
            if not all(item.guess is not None for item in active_players):
                return room, None

            self._finish_room_round(room)
            return room, room.last_round

    def get_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        with self.lock:
            room = self._get_room(room_id, player_id)
            if room.round_deadline is not None and time.time() >= room.round_deadline:
                self._finish_room_round(room)
            return room

    def confirm_room_ready(
        self, room_id: str, player_id: str, ready: bool = True,
    ) -> GeoGuessrRoom:
        with self.lock:
            room = self._get_room(room_id, player_id)
            player = room.players[player_id]
            if player.is_spectator:
                raise ValueError("Les spectateurs ne peuvent pas confirmer leur préparation.")
            if room.status == "lobby":
                player.ready = ready
                return room
            if room.status != "playing" or not room.awaiting_next_round:
                raise ValueError("Aucune confirmation de manche n'est attendue.")

            player.ready = ready
            active_players = [item for item in room.players.values() if not item.is_spectator]
            if all(item.ready for item in active_players):
                self._advance_room_round(room)
            return room

    def _advance_room_round(self, room: GeoGuessrRoom) -> None:
        room.round_index += 1
        room.awaiting_next_round = False
        room.last_round = None
        for player in room.players.values():
            player.guess = None
            player.ready = False
            player.is_spectator = False

    def _finish_room_round(self, room: GeoGuessrRoom) -> None:
        guesses = []
        missed_players = []
        for player in room.players.values():
            if player.guess is None:
                if not player.is_spectator:
                    missed_players.append(player.name)
                continue
            player.total_score += player.guess["score"]
            round_result = {
                "player_id": player.player_id,
                "name": player.name,
                **player.guess,
            }
            player.results.append(round_result)
            guesses.append(round_result)

        room.last_round = {
            "round_number": room.round_index + 1,
            "target": _public_city(room.target),
            "guesses": guesses,
            "missed_players": missed_players,
        }
        room.round_deadline = None
        for player in room.players.values():
            player.ready = False
        if room.round_index + 1 == room.round_count:
            room.round_index += 1
            room.status = "finished"
        else:
            room.awaiting_next_round = True

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            result = []
            for room in self.rooms.values():
                if room.status == "finished":
                    continue
                result.append({
                    "room_id": room.room_id,
                    "player_count": sum(not item.is_spectator for item in room.players.values()),
                    "spectator_count": sum(item.is_spectator for item in room.players.values()),
                    "max_players": MAX_PLAYERS,
                    "status": room.status,
                    "region": room.region,
                    "round_count": room.round_count,
                    "is_member": player_id in room.players if player_id else False,
                })
            return result

    def _get_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        room = self.rooms.get(room_id.strip().upper())
        if not room or player_id not in room.players:
            raise KeyError("Salon introuvable.")
        room.players[player_id].connected = True
        return room


geoguessr_manager = GeoGuessrManager()
