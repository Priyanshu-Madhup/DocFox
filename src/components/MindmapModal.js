import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import './MindmapModal.css';

const MindmapModal = ({ isOpen, onClose, notebookId, documentName }) => {
  const svgRef = useRef();
  const [isLoading, setIsLoading] = useState(false);
  const zoomRef = useRef(null); // Store zoom behavior for reset functionality

  console.log('MindmapModal rendered with:', { isOpen, notebookId, documentName });

  useEffect(() => {
    console.log('MindmapModal useEffect:', { isOpen, notebookId, documentName });
    if (isOpen && notebookId && documentName) {
      // Clear any existing content first
      if (svgRef.current) {
        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove();
      }
      
      // Add a small delay to ensure the modal is fully rendered
      setTimeout(() => {
        generateMindmap();
      }, 100);
    }
    
    // Cleanup when modal closes
    if (!isOpen && svgRef.current) {
      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();
      svg.on('.zoom', null);
    }
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, notebookId, documentName]);

  if (!isOpen) {
    return null;
  }

  const generateMindmap = async () => {
    setIsLoading(true);
    console.log('Starting mindmap generation for:', { notebookId, documentName });
    
    // Clear any existing content immediately
    if (svgRef.current) {
      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();
      svg.on('.zoom', null);
      console.log('Cleared existing SVG content');
    }
    
    try {
      console.log('Fetching summary for specific document:', documentName);
      
      // Get document summary for specific document using document_name parameter
      const response = await fetch(`http://localhost:8001/notebooks/${notebookId}/summary?document_name=${encodeURIComponent(documentName)}`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Summary response for', documentName, ':', data);
      
      if (data.error) {
        throw new Error(data.error);
      }
      
      // Check if no documents were found
      if (data.total_chunks === 0 || data.document_count === 0) {
        console.log('No documents found, showing instructions');
        // Show a helpful tree with instructions
        const instructionTree = {
          name: "No Documents Found",
          children: [
            {
              name: "To Generate Mindmap:",
              children: [
                { name: "1. Upload PDF documents", children: [] },
                { name: "2. Wait for processing", children: [] },
                { name: "3. Click mindmap again", children: [] }
              ]
            },
            {
              name: "Available Actions:",
              children: [
                { name: "• Upload PDFs in right sidebar", children: [] },
                { name: "• Ask questions in chat", children: [] },
                { name: "• Create new notebooks", children: [] }
              ]
            }
          ]
        };
        createD3Tree(instructionTree);
        return;
      }
      
      // Parse the summary and convert to D3 tree structure
      const treeData = parseSummaryToTree(data.summary || 'No content available');
      console.log('Parsed tree data:', treeData);
      
      // Create D3 visualization
      createD3Tree(treeData);
    } catch (error) {
      console.error('Error generating mindmap:', error);
      // Create a helpful error tree structure
      const errorTree = {
        name: "Error Loading Mindmap",
        children: [
          {
            name: "Possible Issues:",
            children: [
              { name: "• Backend not running", children: [] },
              { name: "• No documents uploaded", children: [] },
              { name: "• Network connection", children: [] }
            ]
          },
          {
            name: "Try:",
            children: [
              { name: "• Upload some PDFs first", children: [] },
              { name: "• Check console for errors", children: [] },
              { name: "• Refresh the page", children: [] }
            ]
          }
        ]
      };
      createD3Tree(errorTree);
    } finally {
      setIsLoading(false);
    }
  };

  const parseSummaryToTree = (summaryText) => {
    console.log('Parsing summary text:', summaryText?.substring(0, 200));
    
    // Parse the LLM response into a hierarchical structure
    const lines = summaryText.split('\n').filter(line => line.trim());
    
    const root = {
      name: "Document Analysis",
      children: []
    };

    let currentMainTopic = null;
    let currentSubtopic = null;

    lines.forEach(line => {
      const trimmed = line.trim();
      
      // Skip empty lines or very short lines
      if (trimmed.length < 3) return;
      
      // Main sections (starting with **number. or **text**)
      if (trimmed.match(/^\*\*\d+\.\s+.*\*\*/) || trimmed.match(/^\*\*[^*]+\*\*$/)) {
        const topicName = trimmed.replace(/\*\*/g, '').replace(/^\d+\.\s*/, '').trim();
        
        currentMainTopic = {
          name: topicName.substring(0, 40) + (topicName.length > 40 ? '...' : ''),
          children: []
        };
        root.children.push(currentMainTopic);
        currentSubtopic = null;
        console.log('Found main topic:', topicName);
      }
      // Subsections (starting with - **text**)
      else if (trimmed.match(/^-\s*\*\*.*\*\*/) && currentMainTopic) {
        const subtopicName = trimmed.replace(/^-\s*/, '').replace(/\*\*/g, '').trim();
        
        currentSubtopic = {
          name: subtopicName.substring(0, 35) + (subtopicName.length > 35 ? '...' : ''),
          children: []
        };
        currentMainTopic.children.push(currentSubtopic);
        console.log('Found subtopic:', subtopicName);
      }
      // Bullet points (starting with â¢ or •)
      else if (trimmed.match(/^\s*[â¢•]\s*/) && (currentSubtopic || currentMainTopic)) {
        const pointName = trimmed.replace(/^\s*[â¢•]\s*/, '').trim();
        
        if (pointName.length > 5) {
          const pointNode = {
            name: pointName.substring(0, 50) + (pointName.length > 50 ? '...' : ''),
            children: []
          };
          
          if (currentSubtopic) {
            currentSubtopic.children.push(pointNode);
          } else if (currentMainTopic) {
            currentMainTopic.children.push(pointNode);
          }
          console.log('Found bullet point:', pointName.substring(0, 30));
        }
      }
      // Additional content lines
      else if (trimmed.length > 10 && currentMainTopic && !trimmed.match(/^[\s\-*]+$/)) {
        const cleanLine = trimmed.replace(/[^\w\s:.,()-]/g, '').trim();
        if (cleanLine.length > 8) {
          const lineNode = {
            name: cleanLine.substring(0, 45) + (cleanLine.length > 45 ? '...' : ''),
            children: []
          };
          
          if (currentSubtopic) {
            currentSubtopic.children.push(lineNode);
          } else {
            currentMainTopic.children.push(lineNode);
          }
        }
      }
    });

    // If no structure was parsed, create a basic structure
    if (root.children.length === 0) {
      console.log('No structure found, creating basic tree');
      root.children.push({
        name: "Document Content",
        children: [
          { name: "Main Information", children: [] },
          { name: "Key Details", children: [] }
        ]
      });
    }

    console.log('Final tree structure:', root);
    return root;
  };

  const createD3Tree = (data) => {
    console.log('Creating D3 tree with data for document:', documentName, data);
    
    // Wait for SVG to be available
    if (!svgRef.current) {
      console.error('SVG ref is null, retrying in 100ms...');
      setTimeout(() => createD3Tree(data), 100);
      return;
    }
    
    const svg = d3.select(svgRef.current);
    
    // Aggressively clear all previous content
    console.log('Clearing all previous SVG content...');
    svg.selectAll("*").remove();
    svg.on('.zoom', null); // Remove any existing zoom handlers
    svg.on('wheel', null); // Remove wheel handlers
    svg.on('mousedown', null); // Remove mouse handlers
    
    // Reset SVG properties
    svg.attr("width", null)
       .attr("height", null)
       .style("background", null)
       .style("border", null);

    const container = svgRef.current.parentElement;
    if (!container) {
      console.error('Container not found, using default dimensions');
    }
    
    const width = container ? Math.max(1400, container.clientWidth) : 1400; // Larger canvas for more spacing
    const height = container ? Math.max(1000, container.clientHeight) : 1000; // Larger canvas for more spacing
    const margin = { top: 80, right: 200, bottom: 80, left: 200 }; // Larger margins

    console.log('SVG dimensions:', { width, height });

    svg.attr("width", width)
       .attr("height", height)
       .style("background", "#1e1e1e")
       .style("border", "2px solid #444");

    // Create the group element first
    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Add zoom and pan functionality with better sensitivity
    const zoom = d3.zoom()
      .scaleExtent([0.1, 5]) // Increased max zoom level
      .on("zoom", (event) => {
        g.attr("transform", `translate(${margin.left + event.transform.x},${margin.top + event.transform.y}) scale(${event.transform.k})`);
      });

    svg.call(zoom);
    zoomRef.current = zoom; // Store zoom for reset functionality
    
    // Position the tree towards right and bottom for better visibility
    svg.call(zoom.transform, d3.zoomIdentity.scale(1.2).translate(-200, 100));

    const treeLayout = d3.tree()
      .size([height - margin.top - margin.bottom, width - margin.left - margin.right]) // Reduced spacing for tighter layout
      .separation((a, b) => (a.parent === b.parent ? 1.5 : 2)); // Reduced separation for closer nodes

    const root = d3.hierarchy(data);
    let i = 0; // Move counter to before it's used
    
    // Assign IDs to all nodes
    root.descendants().forEach(d => {
      d.id = d.id || ++i;
    });
    
    console.log('Hierarchy created:', root);
    
    // Collapse all nodes beyond the first level (like Google's mindmaps)
    // Do this BEFORE applying the tree layout
    function collapse(d) {
      if (d.children) {
        // Collapse nodes at depth 1 and beyond (only show root's immediate children)
        if (d.depth >= 1) {
          d._children = d.children;
          d.children = null;
        } else {
          // For root (depth 0), process its children
          d.children.forEach(collapse);
        }
      }
    }
    
    collapse(root);
    
    treeLayout(root);
    console.log('Tree layout applied, descendants:', root.descendants().length);

    // Store initial positions
    root.descendants().forEach(d => {
      d.x0 = d.x;
      d.y0 = d.y;
    });

    // Add links
    g.selectAll(".link")
      .data(root.links())
      .enter().append("path")
      .attr("class", "link")
      .attr("d", d3.linkHorizontal()
        .x(d => d.y)
        .y(d => d.x))
      .style("fill", "none")
      .style("stroke", "#888")
      .style("stroke-width", "2px")
      .style("opacity", 0.8);

    // Add nodes
    const node = g.selectAll(".node")
      .data(root.descendants())
      .enter().append("g")
      .attr("class", d => "node" + (d.children ? " node--internal" : " node--leaf"))
      .attr("transform", d => `translate(${d.y},${d.x})`)
      .style("cursor", "pointer")
      .on("click", (event, d) => toggleNode(event, d, data));

    // Add rectangles for nodes
    node.append("rect")
      .attr("width", d => {
        // Calculate width based on text length
        const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
        return Math.max(80, textLength * 8 + 20); // Minimum 80px, plus padding
      })
      .attr("height", 30)
      .attr("x", d => {
        const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
        const width = Math.max(80, textLength * 8 + 20);
        return -width / 2; // Center the rectangle
      })
      .attr("y", -15) // Center vertically
      .attr("rx", 5) // Rounded corners
      .attr("ry", 5)
      .style("fill", d => d.children ? "rgba(66, 133, 244, 0.5)" : "rgba(52, 168, 83, 0.5)")
      .style("stroke", "#fff")
      .style("stroke-width", "2px")
      .style("opacity", 0.9);

    // Add text labels
    node.append("text")
      .attr("dy", 5) // Center vertically in the rectangle
      .attr("x", 0) // Center horizontally
      .style("text-anchor", "middle")
      .text(d => d.data.name.length > 25 ? d.data.name.substring(0, 25) + '...' : d.data.name)
      .style("font-size", "12px")
      .style("font-family", "Arial, sans-serif")
      .style("fill", "#ffffff")
      .style("font-weight", "500")
      .style("opacity", 1);

    function toggleNode(event, d, originalData) {
      console.log('Toggling node:', d.data.name);
      if (d.children) {
        d._children = d.children;
        d.children = null;
      } else {
        d.children = d._children;
        d._children = null;
      }
      
      // Update the tree with animation
      update(d, originalData);
    }
    
    function update(source, originalData) {
      const duration = 300;
      
      // Recompute the layout
      treeLayout(root);
      
      // Update links
      const link = g.selectAll(".link")
        .data(root.links(), d => d.target.id);
        
      link.enter().append("path")
        .attr("class", "link")
        .attr("d", d3.linkHorizontal()
          .x(d => source.y0 || source.y)
          .y(d => source.x0 || source.x))
        .style("fill", "none")
        .style("stroke", "#888")
        .style("stroke-width", "2px")
        .style("opacity", 0)
        .transition()
        .duration(duration)
        .attr("d", d3.linkHorizontal()
          .x(d => d.y)
          .y(d => d.x))
        .style("opacity", 0.8);
        
      link.transition()
        .duration(duration)
        .attr("d", d3.linkHorizontal()
          .x(d => d.y)
          .y(d => d.x))
        .style("opacity", 0.8);
        
      link.exit().transition()
        .duration(duration)
        .style("opacity", 0)
        .remove();
      
      // Update nodes
      const nodeUpdate = g.selectAll(".node")
        .data(root.descendants(), d => d.id);
        
      // Enter new nodes
      const nodeEnter = nodeUpdate.enter().append("g")
        .attr("class", d => "node" + (d.children ? " node--internal" : " node--leaf"))
        .attr("transform", d => `translate(${source.y0 || source.y},${source.x0 || source.x})`)
        .style("cursor", "pointer")
        .style("opacity", 0)
        .on("click", (event, d) => toggleNode(event, d, originalData));
        
      // Add rectangles to new nodes
      nodeEnter.append("rect")
        .attr("width", 0)
        .attr("height", 0)
        .attr("x", 0)
        .attr("y", 0)
        .attr("rx", 5)
        .attr("ry", 5)
        .style("fill", d => d.children ? "rgba(66, 133, 244, 0.5)" : "rgba(52, 168, 83, 0.5)")
        .style("stroke", "#fff")
        .style("stroke-width", "2px")
        .transition()
        .duration(duration)
        .attr("width", d => {
          const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
          return Math.max(80, textLength * 8 + 20);
        })
        .attr("height", 30)
        .attr("x", d => {
          const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
          const width = Math.max(80, textLength * 8 + 20);
          return -width / 2;
        })
        .attr("y", -15);
        
      // Add text to new nodes
      nodeEnter.append("text")
        .attr("dy", 5)
        .attr("x", 0)
        .style("text-anchor", "middle")
        .text(d => d.data.name.length > 25 ? d.data.name.substring(0, 25) + '...' : d.data.name)
        .style("font-size", "12px")
        .style("font-family", "Arial, sans-serif")
        .style("fill", "#ffffff")
        .style("font-weight", "500")
        .style("opacity", 0)
        .transition()
        .duration(duration)
        .style("opacity", 1);
        
      // Transition entering nodes to their new position
      nodeEnter.transition()
        .duration(duration)
        .attr("transform", d => `translate(${d.y},${d.x})`)
        .style("opacity", 1);
        
      // Update existing nodes
      nodeUpdate.transition()
        .duration(duration)
        .attr("transform", d => `translate(${d.y},${d.x})`)
        .select("rect")
        .attr("width", d => {
          const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
          return Math.max(80, textLength * 8 + 20);
        })
        .attr("height", 30)
        .attr("x", d => {
          const textLength = d.data.name.length > 25 ? 25 : d.data.name.length;
          const width = Math.max(80, textLength * 8 + 20);
          return -width / 2;
        })
        .attr("y", -15)
        .style("fill", d => d.children ? "rgba(66, 133, 244, 0.5)" : "rgba(52, 168, 83, 0.5)");
        
      // Update existing text
      nodeUpdate.select("text")
        .attr("x", 0)
        .style("text-anchor", "middle");
        
      // Exit old nodes
      nodeUpdate.exit().transition()
        .duration(duration)
        .attr("transform", d => `translate(${source.y},${source.x})`)
        .style("opacity", 0)
        .remove();
        
      // Store old positions for transition
      root.descendants().forEach(d => {
        d.x0 = d.x;
        d.y0 = d.y;
      });
    }
  };

  if (!isOpen) {
    console.log('MindmapModal not rendering - isOpen is false');
    return null;
  }

  console.log('MindmapModal rendering modal...');

  return (
    <div className="mindmap-modal-overlay" onClick={onClose}>
      <div className="mindmap-modal" onClick={e => e.stopPropagation()}>
        <div className="mindmap-modal__header">
          <h2>Document Mindmap</h2>
          <button className="mindmap-modal__close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="mindmap-modal__content">
          {isLoading ? (
            <div className="mindmap-modal__loading">
              <div className="loading-spinner"></div>
              <p>Generating mindmap...</p>
            </div>
          ) : (
            <div className="mindmap-container">
              <div className="mindmap-controls">
                <p>Click nodes to expand/collapse • Zoom and pan with mouse • Scroll to zoom</p>
              </div>
              <svg ref={svgRef} className="mindmap-svg"></svg>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MindmapModal;
