// Offline Dijkstra Routing Engine for Emergency Shelters

export interface Node {
  id: string;
  lat: number;
  lon: number;
}

export interface Edge {
  from: string;
  to: string;
  weight: number; // Distance in km
}

export interface RouteResult {
  path: [number, number][]; // Array of [lat, lon] coordinates
  distance: number; // Total distance in km
}

// Mock local road network around target Bihar/Assam regions for offline pathfinding
export const OFFLINE_ROAD_NODES: Node[] = [
  { id: "A", lat: 25.6124, lon: 85.1376 }, // Click Center (Patna)
  { id: "B", lat: 25.6120, lon: 85.1350 }, // Intersection 1
  { id: "C", lat: 25.6105, lon: 85.1330 }, // Intersection 2
  { id: "D", lat: 25.6135, lon: 85.1390 }, // Intersection 3
  { id: "S1", lat: 25.6110, lon: 85.1310 }, // Patna Stadium Shelter (Target)
  
  // Muzaffarpur region nodes
  { id: "M_A", lat: 26.1209, lon: 85.3647 },
  { id: "M_B", lat: 26.1215, lon: 85.3630 },
  { id: "M_S1", lat: 26.1220, lon: 85.3620 } // School Shelter
];

export const OFFLINE_ROAD_EDGES: Edge[] = [
  { from: "A", to: "B", weight: 0.35 },
  { from: "B", to: "C", weight: 0.25 },
  { from: "C", to: "S1", weight: 0.20 },
  { from: "A", to: "D", weight: 0.20 },
  { from: "B", to: "S1", weight: 0.45 },
  
  // Muzaffarpur edges
  { from: "M_A", to: "M_B", weight: 0.22 },
  { from: "M_B", to: "M_S1", weight: 0.12 }
];

export const runDijkstra = (startLat: number, startLon: number, targetLat: number, targetLon: number): RouteResult => {
  // Find nearest starting node in our cached graph
  let startNodeId = "A";
  let minStartDist = Infinity;
  
  // Find nearest target node in our cached graph
  let targetNodeId = "S1";
  let minTargetDist = Infinity;

  const calculateDistance = (lat1: number, lon1: number, lat2: number, lon2: number) => {
    const x = (lon2 - lon1) * Math.cos((lat1 + lat2) / 2.0 * Math.PI / 180.0) * 111.32;
    const y = (lat2 - lat1) * 110.57;
    return Math.sqrt(x * x + y * y);
  };

  for (const node of OFFLINE_ROAD_NODES) {
    const dStart = calculateDistance(startLat, startLon, node.lat, node.lon);
    if (dStart < minStartDist) {
      minStartDist = dStart;
      startNodeId = node.id;
    }
    const dTarget = calculateDistance(targetLat, targetLon, node.lat, node.lon);
    if (dTarget < minTargetDist) {
      minTargetDist = dTarget;
      targetNodeId = node.id;
    }
  }

  // --- Dijkstra Algorithm ---
  const distances: { [key: string]: number } = {};
  const previous: { [key: string]: string | null } = {};
  const nodes = new Set<string>();

  for (const node of OFFLINE_ROAD_NODES) {
    distances[node.id] = node.id === startNodeId ? 0 : Infinity;
    previous[node.id] = null;
    nodes.add(node.id);
  }

  while (nodes.size > 0) {
    // Get node with smallest distance
    let smallestNodeId = Array.from(nodes).reduce((minNode, node) => 
      distances[node] < distances[minNode] ? node : minNode
    );

    if (distances[smallestNodeId] === Infinity || smallestNodeId === targetNodeId) {
      break;
    }

    nodes.delete(smallestNodeId);

    // Find neighbors
    const neighbors = OFFLINE_ROAD_EDGES.filter(e => e.from === smallestNodeId || e.to === smallestNodeId);
    for (const edge of neighbors) {
      const neighborId = edge.from === smallestNodeId ? edge.to : edge.from;
      if (!nodes.has(neighborId)) continue;
      
      const alt = distances[smallestNodeId] + edge.weight;
      if (alt < distances[neighborId]) {
        distances[neighborId] = alt;
        previous[neighborId] = smallestNodeId;
      }
    }
  }

  // Build coordinate path
  const pathCoords: [number, number][] = [];
  let current: string | null = targetNodeId;
  
  while (current) {
    const nodeObj = OFFLINE_ROAD_NODES.find(n => n.id === current);
    if (nodeObj) {
      pathCoords.unshift([nodeObj.lat, nodeObj.lon]);
    }
    current = previous[current];
  }

  // Append actual user GPS coords to start/end of path for precise visual routing
  pathCoords.unshift([startLat, startLon]);
  pathCoords.push([targetLat, targetLon]);

  const totalDist = distances[targetNodeId] === Infinity ? calculateDistance(startLat, startLon, targetLat, targetLon) : distances[targetNodeId];

  return {
    path: pathCoords,
    distance: Math.round(totalDist * 100) / 100
  };
};
