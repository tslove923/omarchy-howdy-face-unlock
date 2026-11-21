// The modern system dlib stores full_object_detection parts as dpoint, not
// point. The crate's old Deref<[Point]> assumed a point-backed vector and is
// both uncompilable and unsound against current dlib. No caller needs it;
// prediction and encoding pass the opaque C++ object directly.
cpp_class!(
    pub unsafe struct FaceLandmarks as "dlib::full_object_detection"
);
