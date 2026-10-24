// G085J - deterministic, presentation-only Future30 "relaxed A" idle pose.
// G008 Hero + G085 shared Backpack/Shop MUST use this SAME rig adjustment.
// No ownership, equipment slot, item registry, animation entitlement or
// character identity is synthesized. A mismatched rig stays unmodified.
const applied=new WeakMap();
function namedBone(root,name){
  const wanted=name.toLowerCase().replace(/[^a-z0-9]/g,"");
  const matches=[];
  root.traverse(node=>{
    if(node.isBone&&node.name.toLowerCase().replace(/[^a-z0-9]/g,"")===wanted)
      matches.push(node);
  });
  return matches.length===1?matches[0]:null;
}
export function relaxCurrentFuture30Pose(root,THREE,{radians=0.58}={}){
  if(!root?.isObject3D||typeof THREE?.Quaternion!=="function")
    throw new Error("g085j_idle_rig_missing");
  if(applied.has(root))return applied.get(root);
  if(!(radians>=0.15&&radians<=0.75))
    throw new Error("g085j_idle_angle_not_admitted");
  const arms=[["L","shoulder.L","hand.L"],["R","shoulder.R","hand.R"]]
    .map(([side,shoulder,hand])=>({side,shoulder:namedBone(root,shoulder),
      hand:namedBone(root,hand)}));
  if(arms.some(a=>!a.shoulder||!a.hand||!a.shoulder.parent)){
    const unsupported=Object.freeze({status:"unsupported_rig",arms_applied:0});
    applied.set(root,unsupported);
    return unsupported;
  }
  root.updateMatrixWorld(true);
  const before=arms.map(a=>{
    const s=a.shoulder.getWorldPosition(new THREE.Vector3());
    const h=a.hand.getWorldPosition(new THREE.Vector3());
    return {dx:h.x-s.x,dy:h.y-s.y,
      shoulder:a.shoulder,hand:a.hand,original:a.shoulder.quaternion.clone()};
  });
  // No broad body retargeting for unknown characters: only an actual
  // horizontally extended arm can be made a relaxed A-pose.
  if(before.some(b=>Math.abs(b.dx)<0.08||!Number.isFinite(b.dx))){
    const unsupported=Object.freeze({status:"unsupported_arm_geometry",arms_applied:0});
    applied.set(root,unsupported);
    return unsupported;
  }
  try{
    for(const b of before){
      b.shoulder.parent.updateWorldMatrix(true,false);
      const parentWorld=b.shoulder.parent.getWorldQuaternion(new THREE.Quaternion());
      const worldRotation=new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0,0,1),Math.sign(b.dx)>0?-radians:radians);
      const parentSpace=parentWorld.clone().invert().multiply(worldRotation)
        .multiply(parentWorld);
      b.shoulder.quaternion.premultiply(parentSpace);
    }
    root.updateMatrixWorld(true);
    const after=before.map(b=>{
      const shoulder=b.shoulder.getWorldPosition(new THREE.Vector3());
      const hand=b.hand.getWorldPosition(new THREE.Vector3());
      return {dy:hand.y-shoulder.y,dx:hand.x-shoulder.x};
    });
    // Guarantee both hands genuinely LOWER rather than apply an axis guess.
    if(before.some((b,i)=>after[i].dy>=b.dy-0.05
      ||Math.abs(after[i].dx)>Math.abs(b.dx)*1.10)){
      throw new Error("pose_geometry_not_relaxed");
    }
    const result=Object.freeze({
      status:"applied",arms_applied:2,
      side_deltas:Object.freeze(arms.map((a,i)=>Object.freeze({
        side:a.side,vertical_delta:+(after[i].dy-before[i].dy).toFixed(4),
        horizontal_before:+before[i].dx.toFixed(4),
        horizontal_after:+after[i].dx.toFixed(4)})))
    });
    applied.set(root,result);
    return result;
  }catch{
    for(const b of before)b.shoulder.quaternion.copy(b.original);
    root.updateMatrixWorld(true);
    const status=Object.freeze({status:"unsupported_rotation",arms_applied:0});
    applied.set(root,status);
    return status;
  }
}
