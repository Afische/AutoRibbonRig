import maya.cmds as cmds
import maya.mel as mel
import os

def countFKControls():
    sel = cmds.ls(sl=True)
    if len(sel) != 2:
        cmds.confirmDialog(title="Selection Error",message="Select exactly 2 controls, the first and last in the fk chain",button=["OK"],defaultButton="OK")
        cmds.error("Select exactly 2 controls, the first and last in the fk chain")
    start, end = cmds.ls(sl=True)
    controlCount = []
    origStart, origEnd = start, end

    while end:
        if cmds.listRelatives(end, shapes=True):
            controlCount.append(end)
        if end == start:
            return controlCount

        parent = cmds.listRelatives(end, parent=True, type="transform")
        end = parent[0] if parent else None

        if end is None and start == origStart:
            start, end = origEnd, origStart
            controlCount = []
            continue 

    cmds.confirmDialog(title="Selection Error",message="The selected controls are not in the same hierarchy chain",button=["OK"],defaultButton="OK")
    cmds.error("The selected controls are not in the same hierarchy chain")

def createPlane(controlCount):
    controls = controlCount
    startCtrl = controls[-1]
    endCtrl   = controls[0]

    # Get world positions from control shapes
    startShape = cmds.listRelatives(startCtrl, shapes=True, type="nurbsCurve")[0]
    startBbox  = cmds.exactWorldBoundingBox(startShape)
    startPos   = [(startBbox[0] + startBbox[3]) * 0.5,(startBbox[1] + startBbox[4]) * 0.5,(startBbox[2] + startBbox[5]) * 0.5]
    endShape = cmds.listRelatives(endCtrl, shapes=True, type="nurbsCurve")[0]
    endBbox  = cmds.exactWorldBoundingBox(endShape)
    endPos   = [(endBbox[0] + endBbox[3]) * 0.5,(endBbox[1] + endBbox[4]) * 0.5,(endBbox[2] + endBbox[5]) * 0.5]

    # Midpoint between start and end controls
    midPos = [(startPos[0] + endPos[0]) * 0.5,(startPos[1] + endPos[1]) * 0.5,(startPos[2] + endPos[2]) * 0.5]

    # Analyze which axis the chain is mostly along
    distanceX = endPos[0] - startPos[0]
    distanceZ = endPos[2] - startPos[2]
    planeLength = (distanceX*distanceX + distanceZ*distanceZ) ** 0.5

    # Get control radius along that axis
    startRadius = max((startBbox[3] - startBbox[0]) * 0.5,(startBbox[5] - startBbox[2]) * 0.5)
    endRadius   = max((endBbox[3] - endBbox[0]) * 0.5,(endBbox[5] - endBbox[2]) * 0.5)
    planeWidth = startRadius + endRadius

    # Create and position NURBS plane
    spans = len(controlCount)-1
    plane = cmds.nurbsPlane(w=1, lr=1, d=3, u=1, v=spans, ax=[0,1,0], ch=False)[0]
    plane = cmds.rename(plane, "c_Ribbon_Plane")

    # Center plane between the two end controls
    cmds.xform(plane, ws=True, t=midPos)

    # Scale along Z so plane ends hit start/end positions
    cmds.setAttr(plane + ".scaleZ", planeLength)
    cmds.setAttr(plane + ".scaleX", planeWidth)
    cmds.setAttr(plane + ".scaleY", planeWidth)

    # Freeze transforms and delete history, optimizeScene with Unknown Nodes disabled
    cmds.makeIdentity(plane, apply=True, translate=True, rotate=True, scale=True)
    cmds.delete(plane, ch=True)
    for n in cmds.ls(type="unknown") or []:
        try:
            cmds.delete(n)
        except:
            pass

    return plane

def createFollicles(plane, controlCount):

    vCount = len(controlCount)
    cmds.select(plane)

    # Create follicles
    # doCreateHair <u> <v> <follicleDensity> <startCurveAttract> <attractCurve> <active> <collisions> <thickness> <bendResistance> <clump> <clumpShape> <edgeBound>
    mel.eval(f'doCreateHair 1 {vCount} 10 0 0 1 0 5 0 1 1 1;')

    # Prevent Cached Playback warning
    hairSystems = cmds.ls(type="hairSystem")
    if hairSystems:
        cmds.setAttr(hairSystems[-1] + ".simulationMethod", 1)

    # Delete unwanted items
    for node in ("nucleus1", "hairSystem1", "pfxHair1"):
        if cmds.objExists(node):
            cmds.delete(node)

    # Delete any non-follicle children under hairSystem1Follicles
    follicleGroup = "hairSystem1Follicles"
    if cmds.objExists(follicleGroup):
        descendants = cmds.listRelatives(follicleGroup, allDescendents=True, fullPath=True) or []
        toDelete = []
        for node in descendants:
            shortName = node.split('|')[-1] 
            if "curve" in shortName:
                toDelete.append(node)
        if toDelete:
            cmds.delete(list(set(toDelete)))

    # Rename follicles
    follicles = cmds.listRelatives("hairSystem1Follicles", children=True, fullPath=True) or []
    follicles = sorted(follicles,key=lambda f: cmds.getAttr(cmds.listRelatives(f, shapes=True, fullPath=True)[0] + ".parameterV"))
    for i, f in enumerate(follicles, start=1):
        cmds.rename(f, "c_Follicle_%d" % i)

    return

def createFollicleJoints(controlCount):
    count = len(controlCount)

    # Find the follicle group and follicles
    follicleGroup = "hairSystem1Follicles"
    if not cmds.objExists(follicleGroup):
        cmds.error("Follicle group not found. Run createFollicles first.")

    follicles = cmds.listRelatives(follicleGroup, children=True, fullPath=True) or []

    # Sort follicles by parameterV
    follicles = sorted(follicles,key=lambda f: cmds.getAttr(cmds.listRelatives(f, shapes=True, fullPath=True)[0] + ".parameterV"))

    # Create the first joint
    baseJoint = cmds.joint(name="c_Follicle_Jt_1")
    joints = [baseJoint]

    # Duplicate remaining joints
    for i in range(2, count + 1):
        j = cmds.duplicate(baseJoint, name=f"c_Follicle_Jt_{i}", po=True)[0]
        joints.append(j)

    # Parent joints under follicles and zero transforms
    for jnt, fol in zip(joints, follicles):
        cmds.parent(jnt, fol)
        cmds.setAttr(jnt + ".translate", 0, 0, 0, type="double3")
        cmds.setAttr(jnt + ".rotate", 0, 0, 0, type="double3")

def parentConstraintFKtoFollicleJoints(controlCount):

    # Get follicle joints
    follicleJoints = cmds.ls("c_Follicle_Jt_*", type="joint")
    if not follicleJoints:
        cmds.error("No c_Follicle_Jt_* joints found. Run createFollicleJoints first.")

    # Sort numerically
    follicleJoints = sorted(follicleJoints, key=lambda x: int(x.split("_")[-1]))

    # controlCount is sorted in reverse but follicle joints go base to tip so reverse it to match direction
    fkControls = controlCount[::-1]

    if len(fkControls) != len(follicleJoints):
        cmds.error("Mismatch: Number of FK controls does not match number of follicle joints!")

    for fk, jnt in zip(fkControls, follicleJoints):
        cmds.parentConstraint(jnt, fk, mo=True)
        print(f"Parent constrained {fk} to {jnt}")

def createRibbonControlJoints(controlCount):
    controls = controlCount[:]
    count = len(controls)

    # Determine control indices for ribbon joints
    interval = 4
    indices = list(range(0, count, interval))

    # Ensure base and tip are included
    if indices[-1] != count - 1:
        indices.append(count - 1)

    # Create joints
    numJoints = len(indices)
    cmds.select(clear=True)
    j1 = cmds.joint(name=f"c_Ribbon_Jt_{numJoints}")
    joints = [j1]

    # Duplicate for remaining joints
    for i in range(2, numJoints + 1):
        nameIndex = numJoints - (i - 1)
        j = cmds.duplicate(j1, name=f"c_Ribbon_Jt_{nameIndex}", po=True)[0]
        joints.append(j)

    # Point-snap joints to corresponding FK control
    for jnt, idx in zip(joints, indices):
        ctrl = controls[idx]
        shape = cmds.listRelatives(ctrl, shapes=True, type="nurbsCurve")[0]
        bbox = cmds.exactWorldBoundingBox(shape)
        pos = [(bbox[0] + bbox[3]) * 0.5,(bbox[1] + bbox[4]) * 0.5,(bbox[2] + bbox[5]) * 0.5]
        cmds.xform(jnt, ws=True, t=pos)
        cmds.setAttr(jnt + ".rotate", 0, 0, 0, type="double3")

    return joints

def bindRibbonSkin():
    # Collect ribbon joints
    ribbonJoints = cmds.ls("c_Ribbon_Jt_*", type="joint")
    if not ribbonJoints:
        cmds.error("No ribbon joints found.")

    # Find the ribbon plane
    plane = "c_Ribbon_Plane"
    if not cmds.objExists(plane):
        cmds.error("Ribbon plane 'c_Ribbon_Plane' not found.")

    # Select joints then the plane
    cmds.select(ribbonJoints, plane)

    # Bind skin with settings matching the UI image
    skin = cmds.skinCluster(
        ribbonJoints,
        plane,
        toSelectedBones=True,     # Bind to selected joints
        bindMethod=0,             # Closest distance
        skinMethod=0,             # Classic linear
        normalizeWeights=1,       # Interactive
        weightDistribution=1,     # Distance
        maximumInfluences=5,      # Max influences
        name="c_Ribbon_SkinCluster"
    )[0]

    # Maintain max influences
    if cmds.objExists(skin + ".maintainMaxInfluences"):
        cmds.setAttr(skin + ".maintainMaxInfluences", 1)

    # Remove unused influences
    if cmds.objExists(skin + ".removeUnusedInfluence"):
        cmds.setAttr(skin + ".removeUnusedInfluence", 1)

    # Allow multiple bind poses
    if cmds.objExists(skin + ".allowMultipleBindPoses"):
        cmds.setAttr(skin + ".allowMultipleBindPoses", 1)

    # Colorize skeleton
    if cmds.objExists(skin + ".colorizeSkeleton"):
        cmds.setAttr(skin + ".colorizeSkeleton", 1)

def importRibbonControl(controlCount):

    projectRoot = cmds.workspace(q=True, rd=True).replace("\\", "/")
    ribbonPath = projectRoot + "Characters/_Creatures/CreatureTest/ctrl/Ctrl_Ribbon.ma"

    # Check if file exists
    if not os.path.exists(ribbonPath):
        cmds.error("Ctrl_Ribbon.ma not found at:\n" + ribbonPath)

    # Import the file
    cmds.file(ribbonPath,i=True,type="mayaAscii",ignoreVersion=True,mergeNamespacesOnClash=True)

    # Find all transforms whose name begins with Ribbon_Ctrl_1
    candidates = cmds.ls("Ribbon_Ctrl*", type="transform")
    if not candidates:
        cmds.error("No Ribbon_Ctrl control found after import.")

    # Remove any false matches (like joints or ribbon plane)
    candidates = [c for c in candidates
                if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    # If multiple exist, pick the last one Maya renamed
    importedCtrl = sorted(candidates, key=len)[-1]

    # Base control radius
    baseCtrl = controlCount[-1]
    baseShape = cmds.listRelatives(baseCtrl, shapes=True, type="nurbsCurve", fullPath=True)[0]
    baseBB = cmds.exactWorldBoundingBox(baseShape)
    baseRadius = max((baseBB[3] - baseBB[0]) * 0.5, (baseBB[5] - baseBB[2]) * 0.5)

    # We want the ribbon control to be twice this radius
    desiredRadius = baseRadius * 4.0

    # Imported control radius (all its curve shapes)
    shapes = cmds.listRelatives(importedCtrl, shapes=True, type="nurbsCurve", fullPath=True)
    if not shapes:
        cmds.error("Ribbon_Ctrl has no nurbsCurve shapes.")

    # Use exactWorldBoundingBox over all shapes at once
    ribbonBB = cmds.exactWorldBoundingBox(shapes)
    ribbonRadius = max((ribbonBB[3] - ribbonBB[0]) * 0.5, (ribbonBB[5] - ribbonBB[2]) * 0.5)

    if ribbonRadius == 0:
        cmds.error("Ribbon control radius is zero; cannot scale.")

    scaleFactor = desiredRadius / ribbonRadius

    # Scale CVs of the imported control
    for s in shapes:
        cmds.scale(scaleFactor, scaleFactor, scaleFactor, s + ".cv[*]", r=True, os=True)

def duplicateRibbonControls(controlCount):
    # Find the imported master control
    candidates = cmds.ls("Ribbon_Ctrl*", type="transform")
    candidates = [c for c in candidates if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    if not candidates:
        cmds.error("Cannot find imported Ribbon_Ctrl_1 control to duplicate.")

    masterCtrl = sorted(candidates, key=len)[-1]

    # Find ribbon joints sorted by numerically
    ribbonJoints = cmds.ls("c_Ribbon_Jt_*", type="joint")
    if not ribbonJoints:
        cmds.error("No c_Ribbon_Jt_* joints found.")
    
    numControls = len(ribbonJoints)
    createdControls = []

    for i in range(numControls):
        # First duplicate without naming
        dup = cmds.duplicate(masterCtrl, rc=True)[0]

        # Now rename it explicitly to Ribbon_Ctrl_#
        cleanName = f"Ribbon_Ctrl_{i+1}"
        dup = cmds.rename(dup, cleanName)

        # Position based on corresponding ribbon joint
        pos = cmds.xform(ribbonJoints[i], q=True, ws=True, t=True)
        cmds.xform(dup, ws=True, t=pos)

        cmds.setAttr(dup + ".rotate", 0, 0, 0, type="double3")
        cmds.makeIdentity(dup, apply=True, translate=True, rotate=True, scale=True)

        createdControls.append(dup)

    # Remove master control
    if cmds.objExists(masterCtrl):
        cmds.delete(masterCtrl)

    return createdControls

def parentRibbonJoints():
    # Find ribbon joints
    ribbonJoints = cmds.ls("c_Ribbon_Jt_*", type="joint")
    if not ribbonJoints:
        cmds.error("No c_Ribbon_Jt_* joints found.")

    # Find ribbon controls
    ribbonCtrls = cmds.ls("Ribbon_Ctrl_*", type="transform")
    ribbonCtrls = [c for c in ribbonCtrls if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    if not ribbonCtrls:
        cmds.error("No Ribbon_Ctrl_* controls found.")

    # Sort both numerically by the trailing number
    ribbonJoints = sorted(ribbonJoints, key=lambda x: int(x.split("_")[-1]))
    ribbonCtrls  = sorted(ribbonCtrls,  key=lambda x: int(x.split("_")[-1]))

    # Ensure matching lengths
    if len(ribbonJoints) != len(ribbonCtrls):
        cmds.error("Number of ribbon joints does not match number of ribbon controls!")

    # Parent each pair
    for jnt, ctrl in zip(ribbonJoints, ribbonCtrls):
        cmds.parent(jnt, ctrl)

    for j in ribbonJoints:
        cmds.setAttr(j + ".drawStyle", 2)

def importRibbonPlacement():
    # Build file path
    projectRoot = cmds.workspace(q=True, rd=True).replace("\\", "/")
    placementPath = projectRoot + "Characters/_Creatures/CreatureTest/ctrl/Ctrl_Ribbon_Placement.ma"

    # Validate file
    if not os.path.exists(placementPath):
        cmds.error("Ctrl_Ribbon_Placement.ma not found at:\n" + placementPath)
    cmds.file(placementPath, i=True, type="mayaAscii", ignoreVersion=True, mergeNamespacesOnClash=True)

    # Find the imported placement control (any nurbsCurve named Ribbon_Placement*)
    candidates = cmds.ls("*Ctrl_Placement*", type="transform") or []
    candidates = [c for c in candidates if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]

    if not candidates:
        cmds.error("No Ribbon Placement control found after import.")

    # Use the newest (last renamed) node
    placementCtrl = sorted(candidates, key=len)[-1]

    # Rename it cleanly
    placementCtrl = cmds.rename(placementCtrl, "Ctrl_Ribbon_Placement")

    # Find body ctrl
    controls = ["tsm3_upper_body", "spine_C0_ik0_ctrl", "body_C0_ctrl", "world_ctrl"]
    worldCtrl = None
    for name in controls:
        if cmds.objExists(name):
            worldCtrl = name
            break
    if not worldCtrl:
        worldCtrls = cmds.ls(type="transform") or []
        priority_contains = ["tsm3_upper_body", "spine_c0_ik0_ctrl", "body_c0_ctrl", "world_ctrl"]
        for needle in priority_contains:
            matches = [w for w in worldCtrls if needle in w.lower()]
            if matches:
                worldCtrl = sorted(matches, key=len)[0]  # prefer cleanest/shortest (good for namespaces)
                break
    if not worldCtrl:
        cmds.error("No body ctrl found")

    # Snap placement control to body ctrl position
    tmp = cmds.pointConstraint(worldCtrl, placementCtrl)[0]
    cmds.delete(tmp)

    # Scale to 2× the size of a ribbon control
    # Get reference size from the FIRST ribbon control in your chain
    ribbonCtrl = "Ribbon_Ctrl_1"
    if not cmds.objExists(ribbonCtrl):
        cmds.error("Ribbon_Ctrl_1 not found. Create ribbon controls first.")

    ribbonShapes = cmds.listRelatives(ribbonCtrl, shapes=True, type="nurbsCurve", fullPath=True)
    ribbonBB = cmds.exactWorldBoundingBox(ribbonShapes)
    ribbonRadius = max(( ribbonBB[3] - ribbonBB[0] ) * 0.5, ( ribbonBB[5] - ribbonBB[2] ) * 0.5)

    desiredRadius = ribbonRadius * 2.0

    # Size of imported placement control
    placementShapes = cmds.listRelatives(placementCtrl, shapes=True, type="nurbsCurve", fullPath=True)
    placementBB = cmds.exactWorldBoundingBox(placementShapes)
    placementRadius = max(( placementBB[3] - placementBB[0] ) * 0.5, ( placementBB[5] - placementBB[2] ) * 0.5)

    if placementRadius == 0:
        cmds.error("Placement control radius is zero; cannot scale.")

    scaleFactor = desiredRadius / placementRadius

    # Scale CVs directly
    for s in placementShapes:
        cmds.scale(scaleFactor, scaleFactor, scaleFactor, s + ".cv[*]", r=True, os=True)

    # Freeze transforms
    cmds.makeIdentity(placementCtrl, apply=True, translate=True, rotate=True, scale=True)

    # Find Ribbon Controls
    ribbonCtrls = cmds.ls("Ribbon_Ctrl_*", type="transform") or []
    ribbonCtrls = [c for c in ribbonCtrls if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]

    if not ribbonCtrls:
        cmds.error("No Ribbon_Ctrl_* controls found to parent.")

    # Sort numerically
    ribbonCtrls = sorted(ribbonCtrls, key=lambda name: int(name.split("_")[-1]))

    for ctrl in ribbonCtrls:
        # Store world position and rotation so parenting does not move the control
        pos = cmds.xform(ctrl, q=True, ws=True, t=True)
        rot = cmds.xform(ctrl, q=True, ws=True, ro=True)

        cmds.parent(ctrl, placementCtrl)

        # Restore world transforms (important)
        cmds.xform(ctrl, ws=True, t=pos)
        cmds.xform(ctrl, ws=True, ro=rot)

def createSineTwistPlanes():
    plane = "c_Ribbon_Plane"
    if not cmds.objExists(plane):
        cmds.error("c_Ribbon_Plane does not exist. Create the ribbon plane first.")

    # Duplicate planes
    sine = cmds.rename(cmds.duplicate(plane, rr=True)[0], "c_Ribbon_Plane_Sine")
    twist = cmds.rename(cmds.duplicate(plane, rr=True)[0], "c_Ribbon_Plane_Twist")

    # Unlock and translate
    for d, offset in [(sine,150), (twist,200)]:
        for attr in ["tx","ty","tz","rx","ry","rz","sx","sy","sz","v"]:
            try: cmds.setAttr(f"{d}.{attr}", lock=False)
            except: 
                pass
        cmds.xform(d, r=True, t=[offset,0,0])

    # Equivalent to selecting twist, then sine, then base and applying blendShape
    cmds.blendShape(twist, sine, plane, n="c_Ribbon_Plane_BS")

    # Create twist deformer
    twistA, twistB = cmds.nonLinear(twist, type="twist", name="RibbonPlane_TwistDef")
    # Determine which returned node is the handle (transform)
    twistHandle = twistA if cmds.nodeType(twistA) == "transform" else twistB
    cmds.setAttr(twistHandle + ".rotateX", -90)

    # Create sine deformer
    sineA, sineB = cmds.nonLinear(sine, type="sine", name="RibbonPlane_SineDef")
    # Determine handle by checking node type
    sineHandle = sineA if cmds.nodeType(sineA) == "transform" else sineB
    cmds.setAttr(sineHandle + ".rotateX", 90)
    cmds.xform(sineHandle, r=True, t=[0, 0, 140])

    # Move skinCluster to top of deformer list
    skinClusters = cmds.ls(cmds.listHistory(plane), type="skinCluster")
    if not skinClusters:
        cmds.error("No skinCluster found on c_Ribbon_Plane.")
    skin = skinClusters[0]

    # Get all deformers on the geometry
    history = cmds.listHistory(plane) or []
    deformers = [d for d in history if cmds.nodeType(d) in ("blendShape","twist","sine","bend","flare","squash","lattice","cluster")]
    for d in deformers:
        if d != skin:
            try:
                cmds.reorderDeformers(skin, d, plane)
            except:
                pass

    return [sine, twist]

def importCtrlX():
    # Build file path
    projectRoot = cmds.workspace(q=True, rd=True).replace("\\", "/")
    ctrlXPath = projectRoot + "Characters/_Creatures/CreatureTest/ctrl/Ctrl_X.ma"
    if not os.path.exists(ctrlXPath):
        cmds.error("Ctrl_X.ma not found at:\n" + ctrlXPath)
    cmds.file(ctrlXPath, i=True, type="mayaAscii", ignoreVersion=True, mergeNamespacesOnClash=True)

    # The imported controls are known by name
    ctrlNames = ["Attribute_Twist_Ctrl", "Attribute_Wave_Ctrl"]

    # Filter for ones that actually exist
    imported = [c for c in ctrlNames if cmds.objExists(c)]
    if not imported:
        cmds.error("Attribute_Twist_Ctrl and Attribute_Wave_Ctrl NOT found after import.")

    # Snap target
    target = "Ribbon_Ctrl_1"
    if not cmds.objExists(target):
        cmds.error("Ribbon_Ctrl_1 does not exist.")
    placement = "Ctrl_Ribbon_Placement"
    if not cmds.objExists(placement):
        cmds.error("Ctrl_Ribbon_Placement does not exist.")

    tempGrp = cmds.group(imported, name="CtrlX_TEMP_GRP")

    # Snap group to Ribbon_Ctrl_1 (keeps internal spacing!)
    tmp = cmds.pointConstraint(target, tempGrp)[0]
    cmds.delete(tmp)

    tmp = cmds.orientConstraint(target, tempGrp)[0]
    cmds.delete(tmp)

    cmds.xform(tempGrp, r=True, t=[50, 50, 0])

    # Freeze transforms on the group (not individual controls)
    cmds.makeIdentity(tempGrp, apply=True, t=True, r=True, s=True)

    # Ungroup and move under Ribbon_Ctrl_1
    cmds.ungroup(tempGrp)
    cmds.parent(imported, placement)

    # Lock Translate, Rotate, Scale channels
    lockAttrs = ["tx","ty","tz","rx","ry","rz","sx","sy","sz"]
    for ctrl in imported:
        for attr in lockAttrs:
            try:
                cmds.setAttr(f"{ctrl}.{attr}", lock=True, keyable=False, channelBox=False)
            except:
                pass

    return imported

def createRibbonSDKs():

    waveCtrl  = "Attribute_Wave_Ctrl"
    twistCtrl = "Attribute_Twist_Ctrl"
    plane     = "c_Ribbon_Plane"
    bsNode    = "c_Ribbon_Plane_BS"
    sineTarget  = "c_Ribbon_Plane_Sine"
    twistTarget = "c_Ribbon_Plane_Twist"

    for n in [waveCtrl, twistCtrl, plane, bsNode]:
        if not cmds.objExists(n):
            cmds.error(f"Required node '{n}' does NOT exist.")

    # Ensure blendshape weights exist
    sineAttr  = f"{bsNode}.{sineTarget}"
    twistAttr = f"{bsNode}.{twistTarget}"

    if not cmds.objExists(sineAttr):
        cmds.error(f"Blendshape target '{sineAttr}' not found.")
    if not cmds.objExists(twistAttr):
        cmds.error(f"Blendshape target '{twistAttr}' not found.")

    # Ensure OFF_ON attribute exists
    for ctrl in [waveCtrl, twistCtrl]:
        if not cmds.attributeQuery("OFF_ON", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="OFF_ON", at="float", min=0, max=1, dv=0, k=True)

    # Wave control blenshape
    # OFF
    cmds.setAttr(f"{waveCtrl}.OFF_ON", 0)
    cmds.setAttr(sineAttr, 0)
    cmds.setDrivenKeyframe(sineAttr, cd=f"{waveCtrl}.OFF_ON")

    # ON
    cmds.setAttr(f"{waveCtrl}.OFF_ON", 1)
    cmds.setAttr(sineAttr, 1)
    cmds.setDrivenKeyframe(sineAttr, cd=f"{waveCtrl}.OFF_ON")

    #  Twist control blendshape
    # OFF
    cmds.setAttr(f"{twistCtrl}.OFF_ON", 0)
    cmds.setAttr(twistAttr, 0)
    cmds.setDrivenKeyframe(twistAttr, cd=f"{twistCtrl}.OFF_ON")

    # ON
    cmds.setAttr(f"{twistCtrl}.OFF_ON", 1)
    cmds.setAttr(twistAttr, 1)
    cmds.setDrivenKeyframe(twistAttr, cd=f"{twistCtrl}.OFF_ON")

    # Make interpolation linear
    for a in [sineAttr, twistAttr]:
        curves = cmds.keyframe(a, q=True, name=True) or []
        for c in curves:
            cmds.keyTangent(c, itt="linear", ott="linear")

def createSineInputSDKs():
    waveCtrl = "Attribute_Wave_Ctrl"
    sineHandle = "RibbonPlane_SineDefHandle"

    if not cmds.objExists(sineHandle):
        cmds.error("RibbonPlane_SineDefHandle does NOT exist!")

    # Get the actual sine deformer node (nonlinear node)
    connections = cmds.listConnections(sineHandle, type="nonLinear") or []
    if not connections:
        cmds.error("Could not find nonlinear deformer node connected to sine handle.")

    sineDef = connections[0]

    # Ensure driver attrs exist
    driverAttrs = ["Amplitude", "Frequency", "Animation", "HeadLock", "TailWave", "CurveDirection"]
    for a in driverAttrs:
        if not cmds.attributeQuery(a, node=waveCtrl, exists=True):
            cmds.addAttr(waveCtrl, ln=a, at="float", dv=0, k=True)

    # SDK mapping (from your screenshot)
    sdkMap = [
        # driverAttr, driverStart, driverEnd,  drivenAttr,  drivenStart, drivenEnd
        ("Amplitude", 0, 7, sineDef, "amplitude", 0, 2),
        ("Frequency", 0, 4, sineDef, "wavelength", 4.5, 0.5),
        ("Animation", 0, 2000, sineDef, "offset", 0, 2000),
        ("HeadLock", 0, 3, sineDef, "dropoff", -1, -0.7),
        ("TailWave", 0, 7, sineDef, "lowBound", -10, -2),
        ("CurveDirection", 0, 1, sineHandle, "rotateZ", 0, 90),
    ]

    # Save all original values
    originalValues = {}
    for driverAttr, dStart, dEnd, drivenNode, drivenAttr, vStart, vEnd in sdkMap:
        plug = f"{drivenNode}.{drivenAttr}"
        originalValues[plug] = cmds.getAttr(plug)

    driverOriginals = {a: cmds.getAttr(f"{waveCtrl}.{a}") for a in driverAttrs}

    # Apply SDKs
    for driverAttr, dStart, dEnd, drivenNode, drivenAttr, vStart, vEnd in sdkMap:

        fullDriver = f"{waveCtrl}.{driverAttr}"
        fullDriven = f"{drivenNode}.{drivenAttr}"

        # Start key
        cmds.setAttr(fullDriver, dStart)
        cmds.setAttr(fullDriven, vStart)
        cmds.setDrivenKeyframe(fullDriven, cd=fullDriver)

        # End key
        cmds.setAttr(fullDriver, dEnd)
        cmds.setAttr(fullDriven, vEnd)
        cmds.setDrivenKeyframe(fullDriven, cd=fullDriver)

        # Linear tangents
        curves = cmds.keyframe(fullDriven, q=True, name=True) or []
        for c in curves:
            cmds.keyTangent(c, itt="linear", ott="linear")

    # Restore original driven values
    for plug, value in originalValues.items():
        cmds.setAttr(plug, value)

    # Restore driver values
    for attr, value in driverOriginals.items():
        cmds.setAttr(f"{waveCtrl}.{attr}", value)

def createTwistInputSDKs():
    twistCtrl = "Attribute_Twist_Ctrl"
    twistHandle = "RibbonPlane_TwistDefHandle"

    if not cmds.objExists(twistHandle):
        cmds.error("RibbonPlane_TwistDefHandle does NOT exist!")

    # Get the actual twist deformer node connected to the handle
    connections = cmds.listConnections(twistHandle, type="nonLinear") or []
    if not connections:
        cmds.error("Could not find nonlinear twist deformer connected to twist handle.")

    twistDef = connections[0]  # this is your twist1 node

    # Ensure driver attributes exist on Attribute_Twist_Ctrl
    driverAttrs = ["StartTwist", "EndTwist"]
    for a in driverAttrs:
        if not cmds.attributeQuery(a, node=twistCtrl, exists=True):
            cmds.addAttr(twistCtrl, ln=a, at="float", dv=0, k=True)

    # SDK mapping derived from your screenshot table
    sdkMap = [
        # driverAttr, driverStart, driverEnd, drivenNode, drivenAttr, drivenStart, drivenEnd
        ("StartTwist", 0, 2000, twistDef, "startAngle", 0, 2000),
        ("EndTwist",   0, 2000, twistDef, "endAngle",   0, 2000),
    ]

    # Store original values for restoration
    originalValues = {}
    for driverAttr, dStart, dEnd, drivenNode, drivenAttr, vStart, vEnd in sdkMap:
        plug = f"{drivenNode}.{drivenAttr}"
        originalValues[plug] = cmds.getAttr(plug)

    driverOriginals = {a: cmds.getAttr(f"{twistCtrl}.{a}") for a in driverAttrs}

    # Create the SDKs
    for driverAttr, dStart, dEnd, drivenNode, drivenAttr, vStart, vEnd in sdkMap:

        fullDriver = f"{twistCtrl}.{driverAttr}"
        fullDriven = f"{drivenNode}.{drivenAttr}"

        # Start key
        cmds.setAttr(fullDriver, dStart)
        cmds.setAttr(fullDriven, vStart)
        cmds.setDrivenKeyframe(fullDriven, cd=fullDriver)

        # End key
        cmds.setAttr(fullDriver, dEnd)
        cmds.setAttr(fullDriven, vEnd)
        cmds.setDrivenKeyframe(fullDriven, cd=fullDriver)

        # Make the curve linear
        curves = cmds.keyframe(fullDriven, q=True, name=True) or []
        for c in curves:
            cmds.keyTangent(c, itt="linear", ott="linear")

    # Restore driven values
    for plug, value in originalValues.items():
        cmds.setAttr(plug, value)

    # Restore driver values
    for attr, value in driverOriginals.items():
        cmds.setAttr(f"{twistCtrl}.{attr}", value)

def cleanupRibbonRig():
    
    groupName = "RibbonRig"
    if cmds.objExists(groupName):
        cmds.delete(groupName)

    nodesToGroup = ["c_Ribbon_Plane","hairSystem1Follicles","Ctrl_Ribbon_Placement","c_Ribbon_Plane_Sine","c_Ribbon_Plane_Twist","RibbonPlane_TwistDefHandle","RibbonPlane_SineDefHandle"]
    nodesToHide = ["c_Ribbon_Plane","hairSystem1Follicles","c_Ribbon_Plane_Sine","c_Ribbon_Plane_Twist","RibbonPlane_TwistDefHandle","RibbonPlane_SineDefHandle"]
    finalNodes = []

    # Collect only existing nodes
    for n in nodesToGroup:
        if cmds.objExists(n):
            finalNodes.append(n)

    if not finalNodes:
        cmds.error("No Ribbon Rig nodes found to group!")

    # Create the RibbonRig group
    cmds.group(finalNodes, name=groupName)

    # Hide the nodes listed
    for n in nodesToHide:
        if cmds.objExists(n):
            cmds.setAttr(f"{n}.visibility", 0)

    # Change control colors
    ribbonCtrls = cmds.ls("Ribbon_Ctrl_*", type="transform") or []
    ribbonCtrls = [c for c in ribbonCtrls if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    placement = ["Ctrl_Ribbon_Placement"]
    ribbonCtrls = ribbonCtrls+placement
    for ctrl in ribbonCtrls:
        if not cmds.objExists(ctrl):
            continue
        shapes = cmds.listRelatives(ctrl, shapes=True, type="nurbsCurve") or []
        for s in shapes:
            cmds.setAttr(s + ".overrideEnabled", 1)
            cmds.setAttr(s + ".overrideColor", 17)
            
    # Parent constraint placement group to body control
    placement = "Ctrl_Ribbon_Placement"
    placementGrp = placement + "_grp"
    parent = cmds.listRelatives(placement, parent=True, fullPath=True)
    parent = parent[0] if parent else None
    placementGrp = cmds.group(em=True, name=placementGrp)
    cmds.delete(cmds.parentConstraint(placement, placementGrp, mo=False))
    placementGrp = cmds.parent(placementGrp, parent)[0]
    m = cmds.xform(placement, q=True, m=True)
    cmds.xform(placementGrp, m=m)
    cmds.parent(placement, placementGrp)
    cmds.setAttr(placement + ".translate", 0, 0, 0, type="double3")
    cmds.setAttr(placement + ".rotate", 0, 0, 0, type="double3")
    cmds.setAttr(placement + ".scale", 1, 1, 1, type="double3")
    # match placementGrp pivot to placement control pivot
    piv = cmds.xform(placement, q=True, ws=True, rp=True)
    cmds.xform(placementGrp, ws=True, rp=piv)
    cmds.xform(placementGrp, ws=True, sp=piv)
    # Lock and hide scale and visibility on all controls
    for ctrl in ribbonCtrls:
        if not cmds.objExists(ctrl):
            continue
        for attr in ["sx", "sy", "sz"]:
            try:
                cmds.setAttr(f"{ctrl}.{attr}", lock=True, keyable=False, channelBox=False)
            except:
                pass
        try:
            cmds.setAttr(f"{ctrl}.v", keyable=False, channelBox=False)
        except:
            pass

    bodyCtrl = cmds.ls(type="transform") or []
    worldCandidates = [w for w in bodyCtrl if "tsm3_upper_body" in w.lower()]
    if not worldCandidates:
        worldCandidates = [w for w in bodyCtrl if "spine_c0_ik0_ctrl" in w.lower()]
        if not worldCandidates:
            worldCandidates = [w for w in bodyCtrl if "body_c0_ctrl" in w.lower()]
            if not worldCandidates:
                worldCandidates = [w for w in bodyCtrl if "world_ctrl" in w.lower()]
                if not worldCandidates:
                    cmds.error("No body ctrl found")
    bodyCtrl = worldCandidates[0]
  
    # Create local/world space switch on the placement control along with parent constraint
    addPlacementSpaceSwitch(placement=placement, localTarget=bodyCtrl)

def addPlacementSpaceSwitch(placement="Ctrl_Ribbon_Placement", localTarget=None):

    # Find world ctrl
    allXforms = cmds.ls(type="transform") or []
    worldMatches = [n for n in allXforms if "world_ctrl" in n.lower()]
    if not worldMatches:
        cmds.error("world_ctrl not found for world space switch")
    worldTarget = sorted(worldMatches, key=len)[0]

    if not localTarget or not cmds.objExists(localTarget):
        cmds.error("localTarget not provided or does not exist for space switch")

    placementGrp = placement + "_grp"

    # pivot constraint
    pcon = cmds.pointConstraint(localTarget, placementGrp, mo=True)[0]

    # scale constraint
    scon = cmds.scaleConstraint(localTarget, placementGrp, mo=True)[0]

    # rotation with space switching
    ocon = cmds.orientConstraint(localTarget, worldTarget, placementGrp, mo=True)[0]

    # Add enum attr space: Local / World
    if not cmds.attributeQuery("space", node=placement, exists=True):
        cmds.addAttr(placement, ln="space", at="enum", en="Local:World", k=True)

    # Weight aliases (order matches targets passed into orientConstraint)
    w_aliases = cmds.orientConstraint(ocon, q=True, wal=True)
    if not w_aliases or len(w_aliases) < 2:
        cmds.error("Could not query orientConstraint weight aliases")

    localW = f"{ocon}.{w_aliases[0]}"
    worldW = f"{ocon}.{w_aliases[1]}"

    # Set driven keys
    # space=0 => local rot
    cmds.setAttr(f"{placement}.space", 0)
    cmds.setAttr(localW, 1)
    cmds.setAttr(worldW, 0)
    cmds.setDrivenKeyframe(localW,  cd=f"{placement}.space")
    cmds.setDrivenKeyframe(worldW, cd=f"{placement}.space")

    # space=1 => world rot
    cmds.setAttr(f"{placement}.space", 1)
    cmds.setAttr(localW, 0)
    cmds.setAttr(worldW, 1)
    cmds.setDrivenKeyframe(localW,  cd=f"{placement}.space")
    cmds.setDrivenKeyframe(worldW, cd=f"{placement}.space")

    # Linear tangents
    for plug in (localW, worldW):
        curves = cmds.keyframe(plug, q=True, name=True) or []
        for c in curves:
            cmds.keyTangent(c, itt="linear", ott="linear")

    # Default back to Local
    cmds.setAttr(f"{placement}.space", 0)

    return pcon, ocon, scon


def runRibbonRig():
    controlCount = countFKControls()
    plane = createPlane(controlCount)
    createFollicles(plane, controlCount)
    createFollicleJoints(controlCount)
    parentConstraintFKtoFollicleJoints(controlCount)
    createRibbonControlJoints(controlCount)
    bindRibbonSkin()
    importRibbonControl(controlCount)
    duplicateRibbonControls(controlCount)
    parentRibbonJoints()
    importRibbonPlacement()
    createSineTwistPlanes()
    importCtrlX()
    createRibbonSDKs()
    createSineInputSDKs()
    createTwistInputSDKs()
    cleanupRibbonRig()
    print("\nRibbonRig creation Complete!")
