import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import './MindmapModal.css';

const MindmapModal = ({ isOpen, onClose, notebookId }) => {
  const svgRef = useRef();
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isOpen && notebookId) {
      // Add a small delay to ensure the modal is fully rendered
      setTimeout(() => {
        generateMindmap();
      }, 100);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, notebookId]);

  const generateMindmap = async () => {
    setIsLoading(true);
    try {
      console.log('Generating mindmap for notebook:', notebookId);
      
      // Get document summary using the dedicated summary endpoint
      const response = await fetch(`http://localhost:8001/notebooks/${notebookId}/summary`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Summary response:', data);
      
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
      else if (trimmed.length > 10 && currentMainTopic && !trimmed.match(/^[\s\-\*]+$/)) {
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

  const createFallbackTree = () => {
    return {
      name: "Document Analysis",
      children: [
        {
          name: "Main Topics",
          children: [
            { name: "Key Concepts", children: [] },
            { name: "Important Details", children: [] },
            { name: "Research Findings", children: [] }
          ]
        },
        {
          name: "Supporting Information",
          children: [
            { name: "References", children: [] },
            { name: "Examples", children: [] },
            { name: "Data Points", children: [] }
          ]
        }
      ]
    };
  };

  const createD3Tree = (data) => {
    console.log('Creating D3 tree with data:', data);
    
    if (!svgRef.current) {
      console.error('SVG ref is null, cannot create tree');
      return;
    }
    
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove(); // Clear previous content

    const container = svgRef.current.parentElement;
    if (!container) {
      console.error('Container not found, using default dimensions');
    }
    
    const width = container ? Math.max(800, container.clientWidth) : 800;
    const height = container ? Math.max(600, container.clientHeight) : 600;
    const margin = { top: 40, right: 120, bottom: 40, left: 120 };

    console.log('SVG dimensions:', { width, height });

    svg.attr("width", width)
       .attr("height", height)
       .style("background", "#1e1e1e")
       .style("border", "2px solid #444");

    // Add a test rectangle to make sure SVG is visible
    svg.append("rect")
       .attr("x", 10)
       .attr("y", 10)
       .attr("width", 100)
       .attr("height", 30)
       .attr("fill", "#4285f4")
       .attr("stroke", "#fff");

    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const treeLayout = d3.tree()
      .size([height - margin.top - margin.bottom, width - margin.left - margin.right]);

    const root = d3.hierarchy(data);
    console.log('Hierarchy created:', root);
    
    treeLayout(root);
    console.log('Tree layout applied, descendants:', root.descendants().length);

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

    // Add circles for nodes
    node.append("circle")
      .attr("r", d => d.children ? 8 : 5)
      .style("fill", d => d.children ? "#4285f4" : "#34a853")
      .style("stroke", "#fff")
      .style("stroke-width", "2px")
      .style("opacity", 1);

    // Add text labels
    node.append("text")
      .attr("dy", 3)
      .attr("x", d => d.children ? -12 : 12)
      .style("text-anchor", d => d.children ? "end" : "start")
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
          .x(d => d.y)
          .y(d => d.x))
        .style("fill", "none")
        .style("stroke", "#888")
        .style("stroke-width", "2px")
        .style("opacity", 0);
        
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
        .data(root.descendants(), d => d.id || (d.id = ++i));
        
      nodeUpdate.enter().append("g")
        .attr("class", d => "node" + (d.children ? " node--internal" : " node--leaf"))
        .attr("transform", d => `translate(${source.y0 || source.y},${source.x0 || source.x})`)
        .style("cursor", "pointer")
        .on("click", (event, d) => toggleNode(event, d, originalData))
        .append("circle")
        .attr("r", d => d.children ? 8 : 5)
        .style("fill", d => d.children ? "#4285f4" : "#34a853")
        .style("stroke", "#fff")
        .style("stroke-width", "2px");
        
      nodeUpdate.transition()
        .duration(duration)
        .attr("transform", d => `translate(${d.y},${d.x})`);
        
      nodeUpdate.exit().transition()
        .duration(duration)
        .attr("transform", d => `translate(${source.y},${source.x})`)
        .style("opacity", 0)
        .remove();
    }
    
    let i = 0;
  };

  const createTestTree = () => {
    const testData = {
      name: "Test Document",
      children: [
        {
          name: "Section 1",
          children: [
            { name: "Point A", children: [] },
            { name: "Point B", children: [] }
          ]
        },
        {
          name: "Section 2", 
          children: [
            { name: "Point C", children: [] },
            { name: "Point D", children: [] }
          ]
        }
      ]
    };
    createD3Tree(testData);
  };

  if (!isOpen) return null;

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
                <p>Click nodes to expand/collapse • Zoom and pan with mouse</p>
                <button 
                  onClick={createTestTree}
                  style={{
                    marginLeft: '1rem',
                    padding: '0.25rem 0.5rem',
                    background: '#4285f4',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Test Tree
                </button>
                <button 
                  onClick={() => {
                    console.log('Testing API call...');
                    generateMindmap();
                  }}
                  style={{
                    marginLeft: '0.5rem',
                    padding: '0.25rem 0.5rem',
                    background: '#34a853',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Test API
                </button>
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
